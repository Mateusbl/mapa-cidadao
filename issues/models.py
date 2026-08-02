from django.db import models
from django.contrib.gis.db import models as gis_models
from simple_history.models import HistoricalRecords
from django.contrib.auth.models import User
import hashlib
# Create your models here.
class Municipio(models.Model):
    name = models.CharField(max_length=100)
    codigo_ibge= models.CharField(max_length=10, unique=True)
    boundary = gis_models.MultiPolygonField()
    
    
    def __str__(self):
        return self.name
    
    
class IssueManager(models.Manager):
    def get_queryset(self):
        return super().get_queryset().filter(is_deleted=False)

    
class Issue(models.Model):
    title = models.CharField(max_length=200)
    description = models.TextField()
    location = gis_models.PointField()
    municipio = models.ForeignKey(Municipio, on_delete=models.PROTECT)
    created_by = models.ForeignKey(User, on_delete=models.CASCADE)
    created_at = models.DateTimeField(auto_now_add=True)
    is_deleted = models.BooleanField(default=False)
    deleted_at = models.DateTimeField(null=True, blank=True)

    history = HistoricalRecords()

    objects = IssueManager()          # uso normal: Issue.objects.all() já exclui deletados
    all_objects = models.Manager()    # acesso explícito a tudo, incluindo deletados

    def soft_delete(self):
        self.is_deleted = True
        self.deleted_at = timezone.now()
        self.save()

    def __str__(self):
        return self.title
    
    
    
    
class Vote(models.Model):
    issue = models.ForeignKey(Issue, on_delete=models.PROTECT)
    user = models.ForeignKey(User, on_delete=models.PROTECT)
    created_at = models.DateTimeField(auto_now_add=True)
    is_active = models.BooleanField(default=True)
    revoked_at = models.DateTimeField(null=True, blank=True)
    revoked_reason = models.CharField(max_length=200, blank=True)
    
    previous_hash = models.CharField(max_length=64, blank=True, default='')
    record_hash = models.CharField(max_length=64, editable=False, default='')

    history = HistoricalRecords()
    

    
    def compute_hash(self):
        payload = f"{self.issue_id}|{self.user_id}|{self.created_at}|{self.previous_hash}"
        return hashlib.sha256(payload.encode()).hexdigest()
    
    def save(self, *args, **kwargs):
        is_new = self.pk is None
        if is_new:
            last_vote = Vote.objects.order_by('-id').first()
            self.previous_hash = last_vote.record_hash if last_vote else ''
        super().save(*args, **kwargs)
        if is_new:
            self.record_hash = self.compute_hash()
            super().save(update_fields=['record_hash'])

    class Meta:
        unique_together = ('issue', 'user')