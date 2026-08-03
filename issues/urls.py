from django.urls import path
from . import views

app_name = 'issues'

urlpatterns = [
    path('', views.issue_list, name='issue_list'),
    path('issue/<int:pk>/', views.issue_detail, name='issue_detail'),
    path('issue/novo/', views.issue_create, name='issue_create'),
    path('issue/<int:pk>/votar/', views.vote_toggle, name='vote_toggle'),
]
