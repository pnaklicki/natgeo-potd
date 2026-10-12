"""Constants for the National Geographic Photo of the Day integration."""
from datetime import timedelta

DOMAIN = "natgeo_potd"
PAGE_URL = "https://www.nationalgeographic.com/photography/photo-of-the-day"
UPDATE_INTERVAL = timedelta(hours=1)  # the photo changes once a day, so hourly checks are plenty
REQUEST_TIMEOUT = 20
USER_AGENT = "Mozilla/5.0 (X11; Linux x86_64) HomeAssistant-natgeo_potd/1.0"
