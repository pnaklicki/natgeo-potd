# National Geographic Photo of the Day for Home Assistant

A custom integration that shows the National Geographic **Photo of the Day** in Home Assistant.
It checks the official website every hour and downloads the image only when it changes.

## Entities

| Entity | Description |
|---|---|
| `camera.national_geographic_photo_of_the_day` | Today's photo. Attributes: title, photographer, description, page URL, image URL, last fetched. |
| Title | Photo title |
| Photographer | Credited photographer |
| Description | Photo caption (full text in the `full_text` attribute when shortened) |
| Last updated | When the page was last checked (diagnostic) |
| Image size | Size of the downloaded image in KB (diagnostic) |
| API calls / API errors / Last error | Request statistics (diagnostic) |

No account, API key or extra Python packages are required.

## Installation

### HACS (recommended)

1. In HACS open **Custom repositories** and add `https://github.com/pnaklicki/natgeo-potd` with category **Integration**.
2. Find **National Geographic Photo of the Day** in HACS and install it.
3. Restart Home Assistant.
4. Go to **Settings → Devices & services → Add integration** and search for *National Geographic Photo of the Day*.

### Manual

1. Copy `custom_components/natgeo_potd/` into the `custom_components` folder of your Home Assistant configuration.
2. Restart Home Assistant and add the integration as above.

## Dashboard

Use a **Picture Entity** card:

```yaml
type: picture-entity
entity: camera.national_geographic_photo_of_the_day
```

## How it works

Every hour the integration reads the public Photo of the Day page and extracts the image, title,
caption and photographer. If the page layout changes and a value can't be read, the
**Last error** sensor shows the reason and the camera keeps showing the last good photo.

The parsing follows the selectors of the unofficial
[Nat-Geo-Photo-of-the-Day-API](https://github.com/sterlingw/Nat-Geo-Photo-of-the-Day-API) by Sterling Whitley (MIT).
National Geographic does not publish an official API, so the integration may need updates if the site changes.

## Disclaimer

This is an unofficial integration and is not affiliated with National Geographic. Photos remain
the property of their photographers and National Geographic. Please respect the copyright notice
shown on the site.

## License

MIT. See [LICENSE](LICENSE).
