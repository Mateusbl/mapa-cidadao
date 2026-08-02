from django.db import models
from django.contrib.gis.db import models as gis_models

# Create your models here.
class Municipio(models.Model):
    name = models.CharField(max_length=100)
    codigo_ibge= models.CharField(max_length=10, unique=True)
    boundary = gis_models.MultiPolygonField()
    
    
    def __str__(self):
        return self.name
    