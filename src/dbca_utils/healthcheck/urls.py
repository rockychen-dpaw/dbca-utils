from django.urls import path

from . import healthcheck

app_name = "healthcheck"

if healthcheck.HEALTHCHECK_ENABLED:
    urlpatterns = [
        path("healthcheck/healthdata", healthcheck.healthdata_view, name="healthdata"),
        path("healthcheck/workload_healthdata", healthcheck.workload_healthdata_view, name="workload_healthdata"),
    ]
else:
    urlpatterns = []
