from desktop_pet.services.system_monitor import SystemMonitor
from desktop_pet.storage import Settings


def test_system_monitor_is_opt_in_throttled_and_detects_battery_edges(app, tmp_path):
    settings = Settings(tmp_path)
    clock = [0]
    calls = []
    battery = {"percent": 18, "charging": False}

    def sample():
        calls.append(True)
        return {"cpu": 10, "ram": 30, "battery": battery.copy()}

    monitor = SystemMonitor(settings, sampler=sample, clock=lambda: clock[0])
    messages = []
    monitor.notification.connect(
        lambda text, reaction: messages.append((text, reaction))
    )
    monitor.sample()
    assert not calls
    settings.update(system_enabled=True, battery_notifications=True)
    monitor.apply_settings()
    assert monitor.timer.interval() == 30000 and len(calls) == 1
    assert "18%" in messages[0][0]
    monitor.sample()
    assert len(messages) == 1
    battery["charging"] = True
    clock[0] = 601
    monitor.sample()
    assert messages[-1][1] == "tail_wag"
    settings.update(system_enabled=False)
    monitor.apply_settings()
    assert not monitor.timer.isActive()
    monitor.shutdown()
