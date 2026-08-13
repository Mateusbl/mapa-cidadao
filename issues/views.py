from django.contrib.auth.decorators import login_required
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
import json
from django.utils import timezone
from .models import Issue, Vote, Municipio, Report


def issue_list(request):
    issues = Issue.objects.all().select_related('municipio', 'created_by')

    municipio_id = request.GET.get('municipio')
    if municipio_id:
        issues = issues.filter(municipio_id=municipio_id)

    municipios = Municipio.objects.all().order_by('name')
    
    map_points = []
    for issue in issues:
        map_points.append({
            'lat': issue.location.y,
            'lng': issue.location.x,
            'title': issue.title,
            'url': f"/issue/{issue.pk}/"
        })

    return render(request, 'issues/issue_list.html', {
        'issues': issues,
        'municipios': municipios,
        'municipio_selecionado': municipio_id,
        'map_points': map_points,
        'map_points_json': json.dumps(map_points)
    })


def issue_detail(request, pk):
    issue = get_object_or_404(Issue, pk=pk)
    vote_count = Vote.objects.filter(issue=issue, is_active=True).count()

    user_vote = None
    if request.user.is_authenticated:
        user_vote = Vote.objects.filter(issue=issue, user=request.user, is_active=True).first()

    return render(request, 'issues/issue_detail.html', {
        'issue': issue,
        'vote_count': vote_count,
        'user_vote': user_vote,
    })


@login_required
def issue_create(request):
    if request.method == 'POST':
        title = request.POST.get('title')
        description = request.POST.get('description')
        municipio_id = request.POST.get('municipio')
        lat = request.POST.get('lat')
        lng = request.POST.get('lng')

        if not all([title, description, municipio_id, lat, lng]):
            messages.error(request, 'Preencha todos os campos.')
            return redirect('issues:issue_create')

        from django.contrib.gis.geos import Point
        municipio = get_object_or_404(Municipio, pk=municipio_id)

        issue = Issue.objects.create(
            title=title,
            description=description,
            location=Point(float(lng), float(lat)),
            municipio=municipio,
            created_by=request.user,
        )
        messages.success(request, 'Issue criado com sucesso.')
        return redirect('issues:issue_detail', pk=issue.pk)

    municipios = Municipio.objects.all().order_by('name')
    return render(request, 'issues/issue_form.html', {'municipios': municipios})


@login_required
def vote_toggle(request, pk):
    issue = get_object_or_404(Issue, pk=pk)

    existing_vote = Vote.objects.filter(issue=issue, user=request.user).first()

    if existing_vote is None:
        Vote.objects.create(issue=issue, user=request.user)
        messages.success(request, 'Voto registrado.')
    elif existing_vote.is_active:
        # revogação: nunca edita o voto original, já que é append-only —
        # apenas marca is_active=False, o que a trigger permite
        existing_vote.is_active = False
        existing_vote.revoked_at = timezone.now()
        existing_vote.save()
        messages.info(request, 'Voto revogado.')
    else:
        messages.warning(request, 'Este voto já foi revogado anteriormente e não pode ser reativado.')

    return redirect('issues:issue_detail', pk=pk)

def user_is_moderator(user):
    return user.groups.filter(name='Moderadores').exists()


@login_required
def report_issue(request, pk):
    issue = get_object_or_404(Issue, pk=pk)
    if request.method == 'POST':
        reason = request.POST.get('reason', '')
        Report.objects.get_or_create(
            issue=issue, reported_by=request.user,
            defaults={'reason': reason}
        )
        messages.success(request, 'Denúncia registrada. Um moderador vai revisar.')
    return redirect('issues:issue_detail', pk=pk)


@login_required
def moderation_queue(request):
    if not user_is_moderator(request.user):
        messages.error(request, 'Acesso restrito a moderadores.')
        return redirect('issues:issue_list')

    reports = Report.objects.filter(resolved=False).select_related('issue', 'reported_by')
    return render(request, 'issues/moderation_queue.html', {'reports': reports})


@login_required
def moderate_hide(request, report_id):
    if not user_is_moderator(request.user):
        return redirect('issues:issue_list')

    report = get_object_or_404(Report, pk=report_id)
    report.issue.soft_delete()
    report.resolved = True
    report.resolved_by = request.user
    report.resolved_at = timezone.now()
    report.save()
    messages.success(request, 'Issue ocultado.')
    return redirect('issues:moderation_queue')


@login_required
def moderate_dismiss(request, report_id):
    if not user_is_moderator(request.user):
        return redirect('issues:issue_list')

    report = get_object_or_404(Report, pk=report_id)
    report.resolved = True
    report.resolved_by = request.user
    report.resolved_at = timezone.now()
    report.save()
    messages.info(request, 'Denúncia descartada, issue mantido.')
    return redirect('issues:moderation_queue')
