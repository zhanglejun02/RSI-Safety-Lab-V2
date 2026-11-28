"""Small versioned selection manifests; no datasets, execution or scoring here."""
from copy import deepcopy
from importlib.resources import files
import json

from rsi_lab.errors import ValidationError
from rsi_lab.serialization import digest


def manifest():
    return json.loads(files('rsi_lab.data').joinpath('task_pools_v1.json').read_text())


def task_pool(name, *, allocation='study', data_dir=None):
    """Resolve IDs into an ordinary training config before freezing a run."""
    pools = manifest()['pools']
    if type(name) is not str or name not in pools:
        raise ValidationError('Unknown task pool: ' + str(name))
    choices = pools[name]['allocations']
    if type(allocation) is not str or allocation not in choices:
        raise ValidationError(f'{name} supports allocations: {", ".join(choices)}')
    result = deepcopy(choices[allocation])
    if data_dir is not None:
        if 'data_dir' not in result or type(data_dir) is not str or not data_dir:
            raise ValidationError('data_dir only applies to a local dataset-backed pool')
        result['data_dir'] = data_dir
    return result


def resolve_training(training):
    if type(training) is not dict or 'pool' not in training:
        return deepcopy(training)
    if set(training) - {'pool', 'allocation', 'data_dir'}:
        raise ValidationError('Choose a locked pool or explicit task IDs, not both')
    return task_pool(training['pool'], allocation=training.get('allocation', 'study'),
                     data_dir=training.get('data_dir'))


def describe_pools():
    data = manifest()
    return {'protocol': data['protocol'], 'manifest_sha256': digest(data), 'stage': data['stage'],
            'pools': {name: {k: deepcopy(value[k]) for k in ('benchmark', 'size', 'role', 'readiness', 'decisions')}
                      for name, value in data['pools'].items()}}
