"""Read-only, opt-in system sampling. Never inspect processes or application content."""
import sys
import time
from PySide6.QtCore import QObject, Signal, QTimer


def windows_battery():
    if sys.platform!='win32': return None
    import ctypes
    class PowerStatus(ctypes.Structure):
        _fields_=[('ACLineStatus',ctypes.c_ubyte),('BatteryFlag',ctypes.c_ubyte),
                 ('BatteryLifePercent',ctypes.c_ubyte),('SystemStatusFlag',ctypes.c_ubyte),
                 ('BatteryLifeTime',ctypes.c_ulong),('BatteryFullLifeTime',ctypes.c_ulong)]
    state=PowerStatus()
    if not ctypes.windll.kernel32.GetSystemPowerStatus(ctypes.byref(state)): return None
    if state.BatteryFlag==128 or state.BatteryLifePercent==255: return None
    return {'percent':state.BatteryLifePercent,'charging':state.ACLineStatus==1}


def collect_stats():
    result={'cpu':None,'ram':None,'battery':None,'source':'Windows power API'}
    try:
        import psutil
        result.update(cpu=psutil.cpu_percent(interval=None),ram=psutil.virtual_memory().percent,source='psutil')
        battery=psutil.sensors_battery()
        if battery is not None:
            result['battery']={'percent':battery.percent,'charging':battery.power_plugged}
    except ImportError:
        result['note']='Install the optional system extra for CPU/RAM monitoring.'
    except (OSError,RuntimeError):
        result['note']='Some system indicators are unavailable.'
    if result['battery'] is None:
        try: result['battery']=windows_battery()
        except (AttributeError,OSError): pass
    return result


class SystemMonitor(QObject):
    updated=Signal(dict)
    notification=Signal(str,str)
    status=Signal(str)
    def __init__(self,settings,parent=None,sampler=collect_stats,clock=time.monotonic):
        super().__init__(parent)
        self.settings=settings;self.sampler=sampler;self.clock=clock
        self.timer=QTimer(self);self.timer.timeout.connect(self.sample)
        self.previous_battery=None;self.last_notice=-float('inf')

    def apply_settings(self):
        self.timer.stop()
        if self.settings.get('system_enabled'):
            self.timer.start(30000);self.sample()
        else: self.status.emit('System monitoring is off.')

    def sample(self):
        if not self.settings.get('system_enabled'): return
        try: data=self.sampler()
        except (OSError,RuntimeError) as exc:
            self.status.emit('System indicators are unavailable.');return
        self.updated.emit(data)
        battery=data.get('battery')
        if battery and self.settings.get('battery_notifications'):
            previous=self.previous_battery
            low=battery['percent']<=20 and not battery['charging']
            became_low=low and (previous is None or previous['percent']>20 or previous['charging'])
            charging=battery['charging'] and previous is not None and not previous['charging']
            if (became_low or charging) and self.clock()-self.last_notice>=600:
                self.last_notice=self.clock()
                self.notification.emit('Charging — a little energy boost!' if charging else
                                       f"Battery at {battery['percent']:.0f}%. Time to plug in?",
                                       'tail_wag' if charging else 'yawning')
        self.previous_battery=battery

    def shutdown(self): self.timer.stop()
