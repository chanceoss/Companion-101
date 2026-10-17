"""Activity metadata shared by native controls, tray actions, and pet behavior."""
from dataclasses import dataclass


@dataclass(frozen=True)
class Activity:
    key: str
    title: str
    scene: str
    color: str
    description: str


ACTIVITIES = (
    Activity("explore", "Explore", "exploring", "#fae8c9",
             "A curious little stroll around your screen, with time to look around."),
    Activity("work", "Work with me", "working", "#f4e3e1",
             "A quiet laptop buddy and a 25-minute focus session. Select again to stop."),
    Activity("greet", "Say hi", "greeting", "#fde1d8",
             "A happy hello and a few hearts, then back to what we were doing."),
    Activity("nap", "Take a nap", "sleeping", "#e5edf0",
             "Curl up for a peaceful nap. Select again to wake up."),
    Activity("follow", "Follow me", "following", "#fae6d2",
             "Follow your mouse gently on this screen, leaving room around the pointer."),
)
BY_KEY = {activity.key: activity for activity in ACTIVITIES}
SCENES = {activity.key: activity.scene for activity in ACTIVITIES}
SCENES["idle"] = "idle"
