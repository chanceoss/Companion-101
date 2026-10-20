"""Small expandable settings groups for optional services."""
from PySide6.QtWidgets import (QCheckBox,QFormLayout,QLabel,QSpinBox,QToolBox,QVBoxLayout,QWidget)


class FeatureSettings(QWidget):
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
        return {key:control.isChecked() if isinstance(control,QCheckBox) else control.value()
                for key,control in self.controls.items()}
