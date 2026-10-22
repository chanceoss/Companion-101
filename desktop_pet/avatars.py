"""Bundled companion identities; stored IDs never become arbitrary file paths."""

from dataclasses import dataclass


@dataclass(frozen=True)
class Avatar:
    name: str
    title: str
    manifest: str
    description: str


AVATARS = {
    "biscuit": Avatar(
        "Biscuit", "Biscuit · Original companion", "sprites.json",
        "a friendly little orange desktop pet",
    ),
    "tori": Avatar(
        "Tori", "Tori · Tortoise", "tori-sprites.json",
        "a calm, friendly, positive, supportive and curious little green tortoise desktop companion",
    ),
}


def avatar_spec(avatar_id):
    return AVATARS.get(avatar_id, AVATARS["biscuit"])
