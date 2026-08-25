from django.conf import settings
from rest_framework.pagination import PageNumberPagination


class DefaultPagination(PageNumberPagination):
    page_size = getattr(settings, "PAGE_SIZE", 20)
    page_size_query_param = "page_size"
    max_page_size = 100
