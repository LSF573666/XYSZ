import os
from django.apps import AppConfig


class XyszConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'xysz'
    
    # def ready(self):
    #     if not os.environ.get('RUN_MAIN'):
    #         from .tasks import FB_strategy
    #         FB_strategy.delay(init_data)