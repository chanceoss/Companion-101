"""On-demand native tools; the main companion/chat layout stays compact."""
from PySide6.QtCore import Signal
from PySide6.QtWidgets import (QComboBox,QDialog,QHBoxLayout,QLabel,QLineEdit,QPushButton,
                               QStackedWidget,QVBoxLayout,QWidget)


class ToolsDialog(QDialog):
    location_chosen=Signal(dict)
    def __init__(self,settings,weather,monitor,parent=None):
        super().__init__(parent)
        self.settings=settings;self.weather=weather;self.monitor=monitor
        self.setWindowTitle('Biscuit · Little tools');self.setMinimumSize(430,420);self.resize(520,600)
        layout=QVBoxLayout(self)
        self.selector=QComboBox();layout.addWidget(self.selector)
        self.pages=QStackedWidget();layout.addWidget(self.pages,1)
        self.selector.currentIndexChanged.connect(self.pages.setCurrentIndex)
        self.page_ids={}
        self.build_weather();self.build_system()
        close=QPushButton('Close');close.clicked.connect(self.close);layout.addWidget(close)

    def add_page(self,key,title,page):
        self.page_ids[key]=self.pages.addWidget(page);self.selector.addItem(title,key)

    def open_page(self,key):
        self.selector.setCurrentIndex(self.page_ids[key]);self.show();self.raise_();self.activateWindow()

    def build_weather(self):
        page=QWidget();rows=QVBoxLayout(page)
        note=QLabel('Choose your city. Weather goes only to Open-Meteo; precise location is never requested.')
        note.setWordWrap(True);rows.addWidget(note)
        search=QHBoxLayout();self.city=QLineEdit();self.city.setPlaceholderText('City, e.g. Manila')
        button=QPushButton('Search');button.clicked.connect(lambda: self.weather.search(self.city.text()))
        search.addWidget(self.city,1);search.addWidget(button);rows.addLayout(search)
        self.candidates=QComboBox();rows.addWidget(self.candidates)
        use=QPushButton('Use selected city and enable weather');use.clicked.connect(self.choose_city);rows.addWidget(use)
        self.weather_summary=QLabel('Weather is off until you choose a location and enable it.')
        self.weather_summary.setWordWrap(True);rows.addWidget(self.weather_summary)
        self.forecast=QLabel('');self.forecast.setWordWrap(True);rows.addWidget(self.forecast)
        self.weather_status=QLabel('Open-Meteo · CC BY 4.0 · free service for non-commercial use')
        self.weather_status.setWordWrap(True);rows.addWidget(self.weather_status)
        refresh=QPushButton('Refresh weather');refresh.clicked.connect(lambda: self.weather.refresh(force=True));rows.addWidget(refresh)
        rows.addStretch();self.add_page('weather','Weather',page)
        self.weather.locations.connect(self.set_locations)
        self.weather.updated.connect(self.show_weather);self.weather.status.connect(self.weather_status.setText)

    def set_locations(self,places):
        self.candidates.clear()
        for place in places:
            self.candidates.addItem(', '.join(str(place.get(k,'')) for k in ('name','admin1','country') if place.get(k)),place)

    def choose_city(self):
        place=self.candidates.currentData()
        if place: self.location_chosen.emit(place)

    def show_weather(self,data):
        location=self.settings.get('weather_city') or 'Selected city'
        cached=f" · {'stale ' if data.get('stale') else ''}cached {data.get('age_seconds',0)/60:.0f} min ago" if data.get('cached') else ''
        self.weather_summary.setText(f"{location}: {data['temperature']:g}°C · {data['condition']}{cached}\n{data['message']}")
        self.forecast.setText('\n'.join(f"{day['date']}: {day['low']:g}–{day['high']:g}°C · {day['rain']}% chance of rain" for day in data['forecast']))

    def build_system(self):
        page=QWidget();rows=QVBoxLayout(page)
        self.system_summary=QLabel('Enable system monitoring in Preferences to view indicators.')
        self.system_summary.setWordWrap(True);rows.addWidget(self.system_summary)
        refresh=QPushButton('Refresh indicators');refresh.clicked.connect(self.monitor.sample);rows.addWidget(refresh)
        note=QLabel('Read-only · sampled every 30 seconds · stays on this device')
        note.setWordWrap(True);rows.addWidget(note);rows.addStretch()
        self.add_page('system','System status',page)
        self.monitor.updated.connect(self.show_system);self.monitor.status.connect(self.system_summary.setText)

    def show_system(self,data):
        lines=[]
        for key,title in (('cpu','CPU'),('ram','RAM')):
            lines.append(f'{title}: {data[key]:.0f}%' if data.get(key) is not None else f'{title}: unavailable')
        battery=data.get('battery')
        lines.append(f"Battery: {battery['percent']:.0f}% · {'charging' if battery['charging'] else 'on battery'}" if battery else 'Battery: unavailable / desktop PC')
        if data.get('note'): lines.append(data['note'])
        self.system_summary.setText('\n'.join(lines))

    def add_voice(self,voice,recognition):
        page=QWidget();rows=QVBoxLayout(page)
        note=QLabel('Configure local voices, speech Python, and microphone mode in Preferences. Nothing listens until you click Mic.')
        note.setWordWrap(True);rows.addWidget(note)
        status=QLabel('Text only by default');status.setWordWrap(True);rows.addWidget(status)
        voice.status.connect(status.setText);recognition.status.connect(status.setText)
        sample=QPushButton('Speak a sample');sample.clicked.connect(lambda:voice.speak('Hi, I’m Biscuit. A little company for your day.'))
        rows.addWidget(sample)
        stop=QPushButton('Stop speech / recording / download')
        stop.clicked.connect(lambda:(voice.stop(),recognition.cancel(),voice.download_job.cancel(),status.setText('Stopped.')))
        rows.addWidget(stop);rows.addStretch();self.add_page('voice','Voice',page)
