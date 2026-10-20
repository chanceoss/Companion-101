"""Small expandable settings groups for optional services."""
from PySide6.QtCore import Signal
from PySide6.QtWidgets import (QCheckBox,QFormLayout,QLabel,QSpinBox,QToolBox,QVBoxLayout,QWidget,
                              QComboBox,QLineEdit,QDoubleSpinBox,QPushButton,QFileDialog,QHBoxLayout)


class FeatureSettings(QWidget):
    download_requested=Signal(str)
    def __init__(self,settings,parent=None):
        super().__init__(parent)
        self.settings=settings;self.controls={}
        outer=QVBoxLayout(self);outer.setContentsMargins(0,0,0,0)
        self.groups=QToolBox();outer.addWidget(self.groups)
        weather=self.page('Weather')
        self.check(weather,'weather_enabled','Weather from Open-Meteo')
        self.check(weather,'weather_reactions','Gentle weather reactions while resting')
        self.number(weather,'weather_interval','Refresh (minutes)',15,180)
        self.weather_location=QLabel('Choose a city in Tools → Weather. No automatic location access.')
        self.weather_location.setWordWrap(True);weather.addRow(self.weather_location)
        system=self.page('System')
        self.check(system,'system_enabled','Read-only CPU, RAM, and battery indicators')
        self.check(system,'battery_notifications','Battery reminders (paused during focus)')
        self.check(system,'notifications','Allow local reminder notifications')
        note=QLabel('No screenshots, app contents, process control, or remote telemetry. CPU/RAM use the optional psutil extra.')
        note.setWordWrap(True);system.addRow(note)
        voice=self.page('Voice · local and optional')
        self.combo(voice,'voice_mode','Conversation',[('Text only','text'),('Text + spoken replies','spoken'),('Push-to-talk + spoken replies','ptt')])
        self.path(voice,'voice_python','Speech Python','file')
        self.path(voice,'piper_model','Piper voice (.onnx)','voice')
        self.path(voice,'whisper_model','Whisper model folder','folder')
        self.number(voice,'voice_volume','Speech volume (%)',0,100)
        speed=QDoubleSpinBox();speed.setRange(.5,2);speed.setSingleStep(.1);speed.setValue(settings.get('voice_speed') or 1)
        self.controls['voice_speed']=speed;voice.addRow('Speech speed',speed)
        self.check(voice,'voice_muted','Mute spoken replies')
        self.combo(voice,'voice_language','Speech language',[('Auto detect',''),('English','en'),('Filipino / Tagalog','tl')])
        self.combo(voice,'microphone_device','Input device',[('System default','')])
        devices=QPushButton('List microphones');devices.setAutoDefault(False);devices.clicked.connect(self.list_microphones);voice.addRow(devices)
        for kind,title in (('piper','Download Piper voice…'),('whisper','Download Whisper tiny…')):
            button=QPushButton(title);button.setAutoDefault(False)
            button.clicked.connect(lambda checked=False,key=kind:self.download_requested.emit(key));voice.addRow(button)
        note=QLabel('No background listening. Microphone audio stays in memory; recognized text is reviewed before Send. Downloads ask first. See the setup guide for optional packages and model licenses.')
        note.setWordWrap(True);voice.addRow(note)
        productivity=self.page('Reminders and Google')
        self.check(productivity,'reminder_quiet_focus','Hold reminder popups until focus ends')
        zone=QLineEdit(settings.get('reminder_timezone') or '')
        zone.setPlaceholderText('System timezone, or e.g. Asia/Manila')
        self.controls['reminder_timezone']=zone;productivity.addRow('Reminder timezone',zone)
        self.path(productivity,'google_client_file','Desktop OAuth JSON','json')
        self.path(productivity,'google_python','Google Python (optional)','file')
        self.check(productivity,'google_tasks_enabled','Enable an already authorized Google Tasks connection')
        self.check(productivity,'google_calendar_enabled','Enable authorized read-only Calendar (refreshes every 5 minutes)')
        self.check(productivity,'calendar_notifications','Upcoming Google event reminders')
        self.number(productivity,'calendar_reminder_minutes','Minutes before event',0,60)
        note=QLabel('Connect/disconnect accounts in Tools → Google. Tokens stay in the OS credential store. Calendar is read-only; each cloud task write asks first.')
        note.setWordWrap(True);productivity.addRow(note)

    def page(self,title):
        page=QWidget();form=QFormLayout(page)
        form.setFieldGrowthPolicy(QFormLayout.AllNonFixedFieldsGrow)
        form.setRowWrapPolicy(QFormLayout.WrapLongRows)
        self.groups.addItem(page,title)
        return form

    def check(self,form,key,text):
        control=QCheckBox(text);control.setChecked(bool(self.settings.get(key)))
        self.controls[key]=control;form.addRow(control);return control

    def number(self,form,key,title,low,high):
        control=QSpinBox();control.setRange(low,high);control.setValue(self.settings.get(key) or low)
        self.controls[key]=control;form.addRow(title,control);return control

    def values(self):
        result={}
        for key,control in self.controls.items():
            result[key]=(control.isChecked() if isinstance(control,QCheckBox) else
                         control.currentData() if isinstance(control,QComboBox) else
                         control.text().strip() if isinstance(control,QLineEdit) else control.value())
        from .services.reminders import local_zone
        local_zone(result.get('reminder_timezone',''))
        return result

    def combo(self,form,key,title,choices):
        control=QComboBox()
        for text,value in choices:control.addItem(text,value)
        index=control.findData(self.settings.get(key));control.setCurrentIndex(max(0,index))
        self.controls[key]=control;form.addRow(title,control);return control

    def path(self,form,key,title,kind):
        row=QHBoxLayout();control=QLineEdit(self.settings.get(key) or '')
        control.setMinimumWidth(80);row.addWidget(control,1)
        button=QPushButton('Browse');button.setAutoDefault(False);row.addWidget(button)
        def browse():
            path=(QFileDialog.getExistingDirectory(self,'Choose model folder') if kind=='folder' else
                  QFileDialog.getOpenFileName(self,title,'','ONNX voice (*.onnx)' if kind=='voice' else 'JSON (*.json)' if kind=='json' else 'Executable / Python (*)')[0])
            if path:control.setText(path)
        button.clicked.connect(browse);self.controls[key]=control;form.addRow(title,row)

    def list_microphones(self):
        combo=self.controls['microphone_device'];current=combo.currentData()
        combo.clear();combo.addItem('System default','')
        try:
            from PySide6.QtMultimedia import QMediaDevices
            for device in QMediaDevices.audioInputs():combo.addItem(device.description(),bytes(device.id()).hex())
            combo.setCurrentIndex(max(0,combo.findData(current)))
        except (ImportError,RuntimeError):pass
