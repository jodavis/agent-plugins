# `service.yaml` schema

| Field | Type | Required | Notes |
|---|---|---|---|
| `name` | string | yes | kebab-case service name, no placeholder tokens remaining |
| `port` | integer | yes | must not collide with another locally running instance |
| `logging.format` | string | yes | `json` (default) or `text` (documented exception only) |
