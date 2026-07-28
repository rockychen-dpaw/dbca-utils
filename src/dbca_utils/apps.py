from django.apps import AppConfig

from .healthcheck import healthcheck


class DbcaUtilsConfig(AppConfig):
    name = "dbca_utils"

    def ready(self):
        if healthcheck.HEALTHCHECK_ENABLED:
            healthcheck.register_healthcheck_urls()
