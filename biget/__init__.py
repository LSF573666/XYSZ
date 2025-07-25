from biget.celery import app as celery_app

default_app_config = 'xysz.apps.XyszConfig'
__all__ = ('celery_app',)