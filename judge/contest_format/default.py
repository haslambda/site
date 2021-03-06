from datetime import timedelta
from django.core.exceptions import ValidationError
from django.db.models import Max, Min
from django.template.defaultfilters import floatformat
from django.urls import reverse
from django.utils.functional import cached_property
from django.utils.html import format_html
from django.utils.safestring import mark_safe
from django.utils.translation import gettext_lazy
from django.utils.html import avoid_wrapping

from judge.contest_format.base import BaseContestFormat
from judge.contest_format.registry import register_contest_format
from judge.utils.timedelta import nice_repr


def bytesdetailformat(bytes):
    def _format_size(bytes, callback):
        bytes = float(bytes)

        KB = 1 << 10
        MB = 1 << 20
        GB = 1 << 30
        TB = 1 << 40
        PB = 1 << 50

        if bytes < KB:
            return callback('', bytes)
        elif bytes < MB:
            return callback('K', bytes / KB)
        elif bytes < GB:
            return callback('M', bytes / MB)
        elif bytes < TB:
            return callback('G', bytes / GB)
        elif bytes < PB:
            return callback('T', bytes / TB)
        else:
            return callback('P', bytes / PB)

    return avoid_wrapping(_format_size(bytes * 1024, lambda x, y: ['%d %sB', '%.2f %sB'][bool(x)] % (y, x)))


@register_contest_format('default')
class DefaultContestFormat(BaseContestFormat):
    name = gettext_lazy('Default')

    @classmethod
    def validate(cls, config):
        if config is not None and (not isinstance(config, dict) or config):
            raise ValidationError('default contest expects no config or empty dict as config')

    def __init__(self, contest, config):
        super(DefaultContestFormat, self).__init__(contest, config)

    def update_participation(self, participation):
        cumtime = 0
        cumsize = 0
        points = 0
        format_data = {}

        for result in participation.submissions.values('problem_id').annotate(
            points=Max('points'), codesize=Min('codesize'), time=Min('submission__date')
        ):
            dt = (result['time'] - participation.start).total_seconds()
            if result['points']:
                cumtime += dt
                cumsize += result['codesize']
            format_data[str(result['problem_id'])] = {'time': dt, 'codesize': result['codesize'], 'points': result['points']}
            points += result['points']

        participation.cumtime = max(cumtime, 0)
        participation.cumsize = cumsize
        participation.score = points
        participation.format_data = format_data
        participation.save()

    def display_user_problem(self, participation, contest_problem):
        format_data = (participation.format_data or {}).get(str(contest_problem.id))
        if format_data:
            return format_html(
                u'<td class="{state}"><a href="{url}">{points}<div class="solving-time">{codesize}</div></a></td>',
                state=('pretest-' if self.contest.run_pretests_only and contest_problem.is_pretested else '') +
                      self.best_solution_state(format_data['points'], contest_problem.points),
                url=reverse('contest_user_submissions',
                            args=[self.contest.key, participation.user.user.username, contest_problem.problem.code]),
                points=floatformat(format_data['points']),
                codesize=bytesdetailformat(format_data['codesize'])
            )
        else:
            return mark_safe('<td></td>')

    def display_participation_result(self, participation):
        return format_html(
            u'<td class="user-points">{points}<div class="solving-time">{cumtime}</div></td>',
            points=floatformat(participation.score),
            cumtime=bytesdetailformat(participation.cumsize)
        )

    def get_problem_breakdown(self, participation, contest_problems):
        return [(participation.format_data or {}).get(str(contest_problem.id)) for contest_problem in contest_problems]
