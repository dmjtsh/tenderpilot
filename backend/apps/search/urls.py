from django.urls import path
from .views import TenderSearchView, TenderMatchView

urlpatterns = [
    path("", TenderSearchView.as_view(), name="search-tenders"),
    path("match/", TenderMatchView.as_view(), name="search-match"),
]
