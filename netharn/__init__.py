"""
# Command to regenerate the the autogenerated portion of this file
# (Remote the --dry to actually run it)
mkinit netharn --noattrs --dry
"""
__version__ = '0.1.5'

from netharn.device import (XPU,)
from netharn.fit_harn import (FitHarn,)
from netharn.hyperparams import (HyperParams,)
from netharn.monitor import (Monitor,)
from netharn.initializers import (Initializer,)
from netharn.output_shape_for import (OutputShapeFor, OutputShape,
                                      HiddenShapes)
from netharn.receptive_field_for import (ReceptiveFieldFor, ReceptiveField,
                                         HiddenFields)

__extra_all__ = [
    'XPU',
    'FitHarn',
    'HyperParams',
    'Monitor',
    'Initializer',

    'OutputShapeFor',
    'OutputShape',
    'HiddenShapes',

    'ReceptiveFieldFor',
    'ReceptiveField',
    'HiddenFields',
]

## AUTOGENERATED AFTER THIS POINT
from netharn import criterions
from netharn import data
from netharn import device
from netharn import exceptions
from netharn import export
from netharn import fit_harn
from netharn import hyperparams
from netharn import initializers
from netharn import layers
from netharn import metrics
from netharn import mixins
from netharn import models
from netharn import monitor
from netharn import optimizers
from netharn import output_shape_for
from netharn import pred_harn
from netharn import receptive_field_for
from netharn import schedulers
from netharn import util

__all__ = ['FitHarn', 'HiddenFields', 'HiddenShapes', 'HyperParams',
           'Initializer', 'Monitor', 'OutputShape', 'OutputShapeFor',
           'ReceptiveField', 'ReceptiveFieldFor', 'XPU', 'criterions', 'data',
           'device', 'exceptions', 'export', 'fit_harn', 'hyperparams',
           'initializers', 'layers', 'metrics', 'mixins', 'models', 'monitor',
           'optimizers', 'output_shape_for', 'pred_harn',
           'receptive_field_for', 'schedulers', 'util']
