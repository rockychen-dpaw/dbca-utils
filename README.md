# Overview

DBCA Django utility classes and functions.

## Requirements

- Python 3.12 or later
- Django 5.2 or later

## Development

Dependencies for this project are managed using [uv](https://docs.astral.sh/uv/).
With uv installed, change into the project directory and run:

    uv sync

Activate the virtualenv like so:

    source .venv/bin/activate

Run unit tests using `pytest` (or `tox`, to test against multiple Python versions):

    pytest -sv
    tox -v

## Releases

Tagged releases are built and pushed to PyPI automatically using a GitHub
workflow in the project. Update the project version in `pyproject.toml` and
tag the required commit with the same value to trigger a release. Packages
can also be built and uploaded manually to PyPI using [uv](https://docs.astral.sh/uv/guides/publish/#publishing-your-package),
if required:

    uv build
    uv publish

## Installation

1. Install via uv/pip/etc.: `pip install dbca-utils`

## SSO Login Middleware

This will automatically login and create users using headers from an upstream proxy (REMOTE_USER and some others).
The logout view will redirect to a separate logout page which clears the SSO session.

### Usage

Add `dbca_utils.middleware.SSOLoginMiddleware` to `settings.MIDDLEWARE` (after both of
`django.contrib.sessions.middleware.SessionMiddleware` and
`django.contrib.auth.middleware.AuthenticationMiddleware`.
Ensure that `AUTHENTICATION_BACKENDS` contains `django.contrib.auth.backends.ModelBackend`,
as this middleware depends on it for retrieving the logged in user for a session.
Note that the middleware will still work without it, but will reauthenticate the session
on every request, and `request.user.is_authenticated` won't work properly/will be false.

Example:

```python
MIDDLEWARE = [
    ...,
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'dbca_utils.middleware.SSOLoginMiddleware'
    ...,
]
```

## Audit model mixin

`AuditMixin` is an extension of `Django.db.model.Model` that adds a number of additional fields:

- `creator` - FK to `AUTH_USER_MODEL`, used to record the object creator
- `modifier` - FK to `AUTH_USER_MODEL`, used to record who the object was last modified by
- `created` - a timestamp that is set on initial object save
- `modified` - an auto-updating timestamp (on each object save)
  
## Healthcheck feature
### Requirements
  - Django 5.2 or later
  - Declared the default cache and also the cache is shared by all pod instances
    
  ### Usage
  - Install the app 'dbca_utils' in INSTALLED_APPS
  - Service Configuration
      - HEALTHCHECK_CACHE: Optional. the django cache to save healthcheck realted data. default is 'default'; if cache doesn't exist, healthcheck feature will be disabled.
      - HEALTHCHECK_ENABLED: Optional. enable/disable the healthcheck service. default is 'true'
      - CACHE_PREFIX: Optional. used as the prefix of the cache key. default is ''
      - PORT: Optional. The listening port of the web application. default is '8080', used to send request to peer pod instance to get the resouces usage of the peer pod instance.
      - WORKLOADS: Optional. Used if the web app has a fixed replicas.
      - WORKLOAD_DEPLOYMENT: Optional. the workload is deployment if it is true; otherwise it is statefulset. default is 'true'
      - WORKLOAD_FAILED_THRESHOLD: Optional. The number of continuous failed times to decide that a pod is offline.
      - WORKLOAD_VOLUMES: Optional. can be 'disabled', 'false','automatic' or "," separated volume mounted point. default is "automatic". Blob storage is not supported.
          - disabled|false: Don't harvest volume usage data
          - automatic: Detect the persistent volume automatically.
          - "," separated volume mounted points: the volume list
      - HEALTHCHECK_SYSTEMDATA_ENABLED: Enable system resource data
      - HEALTHCHECK_PROCESSDATA_ENABLED: Enable process resource data
  - Endpoints added by this app
      - /healthcheck/healthdata: An endpoint for client to harvest the resources usage data. This endpoint should be cofigured to use basic auth in nginx reverse proxy.
      - /workload/healthcheck/healthdata: An internal endpoint used to get the resource usage of the peer pod instance. This endpoing should not be exposed in nginx reverse proxy.
  - Nginx Configuration.
      - Add a location 'location /healthcheck/' and configure it to use basic auth in nginx.
  - Access the url : https://xxx.dbca.wa.gov.au/healthcheck/healthdata to get the health json data
  - The sample data of the health data:
    
          {
           "workload0":{
              "resources":{
                 "start_time":"2026-07-24T06:10:23",
                 "cpu_total":0.0,
                 "cpu_min":0.0,
                 "cpu_max":0.0,
                 "pmemory_total":292.28125,
                 "pmemory_min":95.53515625,
                 "pmemory_max":100.828125,
                 "vmemory_total":764.12890625,
                 "vmemory_min":207.8671875,
                 "vmemory_max":278.59765625,
                 "processes":3,
                 "process":{
                    "start_time":"2026-07-24T06:10:23",
                    "cpu_num":0,
                    "cpu_pcent":0.0,
                    "pmemory":100.828125,
                    "vmemory":207.8671875,
                    "children":[
                       {
                          "start_time":"2026-07-24T06:10:24",
                          "cpu_num":1,
                          "cpu_pcent":0.0,
                          "pmemory":95.53515625,
                          "vmemory":277.6640625
                       },
                       {
                          "start_time":"2026-07-24T06:10:24",
                          "cpu_num":3,
                          "cpu_pcent":0.0,
                          "pmemory":95.91796875,
                          "vmemory":278.59765625,
                          "currentprocess":true
                       }
                    ]
                 }
              },
              "system":{
                 "cpu_pcent":0.0,
                 "cpucores_pcent":[
                    0.0,
                    0.0,
                    0.0,
                    0.0
                 ],
                 "memory_total":31.279705047607422,
                 "memory_used":12.220211029052734,
                 "memory_pcent":39.06753919339612,
                 "bytes_sent":9028205,
                 "bytes_recv":9246094
              },
              "volumes":{
                 "/app/captcha":{
                    "size":1024,
                    "used":0,
                    "pcent":0.006103515625,
                    "unit":"M"
                 }
              },
              "hostname":"auth2-uat11-5b495b67cb-z8vwj"
           },
           "workload1":{
              "resources":{
                 "start_time":"2026-07-24T06:11:45",
                 "cpu_total":0.0,
                 "cpu_min":0.0,
                 "cpu_max":0.0,
                 "pmemory_total":292.02734375,
                 "pmemory_min":95.4140625,
                 "pmemory_max":100.6171875,
                 "vmemory_total":763.84375,
                 "vmemory_min":207.8359375,
                 "vmemory_max":278.546875,
                 "processes":3,
                 "process":{
                    "start_time":"2026-07-24T06:11:45",
                    "cpu_num":1,
                    "cpu_pcent":0.0,
                    "pmemory":100.6171875,
                    "vmemory":207.8359375,
                    "children":[
                       {
                          "start_time":"2026-07-24T06:11:46",
                          "cpu_num":2,
                          "cpu_pcent":0.0,
                          "pmemory":95.4140625,
                          "vmemory":277.4609375
                       },
                       {
                          "start_time":"2026-07-24T06:11:46",
                          "cpu_num":3,
                          "cpu_pcent":0.0,
                          "pmemory":95.99609375,
                          "vmemory":278.546875,
                       }
                    ]
                 }
              },
              "system":{
                 "cpu_pcent":13.1,
                 "cpucores_pcent":[
                    15.4,
                    12.2,
                    12.0,
                    12.7
                 ],
                 "memory_total":31.279705047607422,
                 "memory_used":12.220211029052734,
                 "memory_pcent":39.06753919339612,
                 "bytes_sent":9099207,
                 "bytes_recv":9055029
              },
              "volumes":{
                 "/app/captcha":{
                    "size":1024,
                    "used":0,
                    "pcent":0.006103515625,
                    "unit":"M"
                 }
              },
              "hostname":"auth2-uat11-5b495b67cb-dpdjp"
           },
           "summary":{
              "cpu_total":0.0,
              "cpu_min":0.0,
              "cpu_max":0.0,
              "process_cpu_min":0.0,
              "process_cpu_max":0.0,
              "pmemory_total":584.30859375,
              "pmemory_min":292.02734375,
              "pmemory_max":292.28125,
              "process_pmemory_min":95.4140625,
              "process_pmemory_max":100.828125,
              "vmemory_total":1527.97265625,
              "vmemory_min":763.84375,
              "vmemory_max":764.12890625,
              "process_vmemory_min":207.8359375,
              "process_vmemory_max":278.59765625,
              "processes_total":6,
              "workloads_running":2,
              "workloads_failed":0
           }
        }
    
        
