# -*- coding: utf-8 -*-
import torch  # NOQA
import torch.nn.functional as F
import torch.nn.modules
from packaging import version
import kwarray


if version.parse(torch.__version__) < version.parse('1.0.0'):
    ELEMENTWISE_MEAN = 'elementwise_mean'
else:
    ELEMENTWISE_MEAN = 'mean'


def _backwards_compat_reduction_kw(size_average, reduce, reduction):
    if size_average is None and reduce is None:
        if reduction == 'none':
            size_average = False
            reduce = False
        elif reduction == ELEMENTWISE_MEAN:
            size_average = True
            reduce = True
        elif reduction == 'sum':
            size_average = False
            reduce = True
        else:
            raise ValueError(reduction + " is not a valid value for reduction")
    else:
        if size_average is None or reduce is None:
            raise Exception(
                'Must specify both size_average and reduce in '
                'torch < 0.4.1, or specify neither and use reduction')
        else:
            if not size_average and not reduce:
                reduction = 'none'
            elif size_average and not reduce:
                reduction = 'none'
            elif size_average and reduce:
                reduction = ELEMENTWISE_MEAN
            elif not size_average and reduce:
                reduction = 'sum'
            else:
                raise ValueError(
                    'Impossible combination of size_average and reduce')
    return size_average, reduce, reduction


def nll_focal_loss(logits, targets, focus, dim, weight=None,
                   ignore_index=None, reduction='none'):
    r"""
    Focal loss given preprocessed logits (log probs) instead of raw outputs

    Args:
        logits (FloatTensor): log-probabilities for each class
        targets (LongTensor): correct class indices for each example
        focus (float): focus factor
        dim (int): class dimension
        weight (FloatTensor): per-class weights

    Example:
        >>> from netharn.criterions.focal import *
        >>> C = 3
        >>> dim = 1
        >>> logits = F.log_softmax(torch.rand(10, C, 11, 12), dim=dim)
        >>> targets = (torch.rand(10, 11, 12) * C).long()
        >>> loss1 = F.nll_loss(logits, targets, reduction='none')
        >>> loss2 = nll_focal_loss(logits, targets, focus=0, dim=dim)
        >>> assert torch.allclose(loss1, loss2)
        >>> logits3 = logits.permute(0, 2, 3, 1)
        >>> loss3 = nll_focal_loss(logits3, targets, focus=0, dim=3)
        >>> assert torch.allclose(loss1, loss3)

        >>> # with perclass weights
        >>> logits = F.log_softmax(torch.rand(8, C, 2, 2), dim=dim)
        >>> targets = (torch.rand(8, 2, 2) * C).long()
        >>> weight = torch.FloatTensor([.1, 1.0, 10.0])
        >>> focus = 2.0
        >>> dim = 1
        >>> ignore_index = 0
        >>> output = nll_focal_loss(logits, targets, focus, dim, weight, ignore_index)

    Benchmark:
        >>> from netharn.criterions.focal import *
        >>> import ubelt as ub
        >>> import torch.nn.functional as F
        >>> import netharn as nh
        >>> B, C = 16, 37
        >>> DIMS = (128, 128)
        >>> dim = 1
        >>> inputs = torch.rand(B, C, *DIMS)
        >>> inputs.requires_grad = True
        >>> logits = F.log_softmax(inputs, dim=dim)
        >>> targets = (torch.rand(B, *DIMS) * C).long()
        >>> #
        >>> ti = ub.Timerit(20, bestof=3, verbose=1, unit='us')
        >>> #
        >>> devices = [
        >>>     nh.XPU.coerce('cuda0'),
        >>>     nh.XPU.coerce('cpu'),
        >>> ]
        >>> #
        >>> # Forward
        >>> for xpu in devices:
        >>>     logits = xpu.move(logits)
        >>>     targets = xpu.move(targets)
        >>>     print(' --- FORWARD ---')
        >>>     print('\n\n--- xpu = {!r} ---\n'.format(xpu))
        >>>     for timer in ti.reset('F.nll_loss'):
        >>>         with timer:
        >>>             loss1 = F.nll_loss(logits, targets, reduction='none')
        >>>             torch.cuda.synchronize()
        >>>     for timer in ti.reset('nll_focal_loss(focus=0)'):
        >>>         with timer:
        >>>             loss2 = nll_focal_loss(logits, targets, focus=0, dim=dim)
        >>>             torch.cuda.synchronize()
        >>>     for timer in ti.reset('nll_focal_loss(focus=2)'):
        >>>         with timer:
        >>>             loss3 = nll_focal_loss(logits, targets, focus=2, dim=dim)
        >>>             torch.cuda.synchronize()
        >>> #
        >>> # Backward
        >>> ti = ub.Timerit(5, bestof=1, verbose=1, unit='ms')
        >>> logits = F.log_softmax(inputs, dim=dim)
        >>> for xpu in devices:
        >>>     print(' --- BACKWARD ---')
        >>>     print('\n\n--- xpu = {!r} ---\n'.format(xpu))
        >>>     for timer in ti.reset('F.nll_loss'):
        >>>         with timer:
        >>>             loss1 = F.nll_loss(logits, targets, reduction='none')
        >>>         loss1.mean().backward(retain_graph=True)
        >>>         torch.cuda.synchronize()
        >>>     for timer in ti.reset('nll_focal_loss(focus=0)'):
        >>>         with timer:
        >>>             loss2 = nll_focal_loss(logits, targets, focus=0.0, dim=dim)
        >>>         loss2.mean().backward(retain_graph=True)
        >>>         torch.cuda.synchronize()
        >>>     for timer in ti.reset('nll_focal_loss(focus=2)'):
        >>>         with timer:
        >>>             loss3 = nll_focal_loss(logits, targets, focus=2.0, dim=dim)
        >>>         loss3.mean().backward(retain_graph=True)
        >>>         torch.cuda.synchronize()
    """
    if focus == 0:
        if ignore_index is None:
            ignore_index = -100
        assert dim == 1
        return F.nll_loss(logits, targets, weight=weight,
                          ignore_index=ignore_index, reduction=reduction)

    # Determine which entry in logits corresponds to the target
    num_classes = logits.shape[dim]
    t = kwarray.one_hot_embedding(targets.data, num_classes, dim=dim)

    # We only need the log(p) component corresponding to the target class
    target_logits = (logits * t).sum(dim=dim)  # sameas logits[t > 0]

    # Modulate the weight of examples based on hardness
    target_p = torch.exp(target_logits)
    w = (1 - target_p).pow(focus)

    # Factor in per-class `weight` to the a per-input weight
    if weight is not None:
        class_weight = weight[targets]
        w *= class_weight

    if ignore_index is not None:
        # remove any loss associated with ignore_label
        ignore_mask = (targets != ignore_index).float()
        w *= ignore_mask

    # Normal cross-entropy computation (but with augmented weights per example)
    # Recall the nll_loss of an aexample is simply its -log probability or the
    # real class, all other classes are not needed (due to softmax magic)
    output = w * -target_logits

    return output


class FocalLoss(torch.nn.modules.loss._WeightedLoss):
    r"""

    Original implementation in [1]

    # Math:
    #     FL(p[t]) = -α[t] * (1 − p[t]) ** γ * log(p[t]).

    .. math::
        FL(p_t) = - \alpha_t * (1 − p[t]) ** γ * log(p[t]).
        focal_loss(x, class) = weight[class] * (-x[class] + log(\sum_j exp(x[j])))

    Args:
        focus (float): Focusing parameter. Equivelant to Cross Entropy when
            `focus == 0`. (Defaults to 2) (Note: this is gamma in the paper)

        weight (Tensor, optional): a manual rescaling weight given to each
           class. If given, it has to be a Tensor of size `C`. Otherwise, it is
           treated as if having all ones.


           Finally we note that α, the weight assigned to the rare class, also
           has a stable range, but it interacts with γ making it necessary to
           select the two together

           This should be set depending on `focus`. See [2] for details.
           In general α should be decreased slightly as γ is increased
           (Note: this is α in the paper)

           α ∈ [0, 1] for class 1 and 1−α for class −1

        size_average (bool, optional): By default, the losses are averaged
           over observations for each minibatch. However, if the field
           size_average is set to ``False``, the losses are instead summed for
           each minibatch. Ignored when reduce is ``False``. Default: ``True``

        reduce (bool, optional): By default, the losses are averaged or summed
           for each minibatch. When reduce is ``False``, the loss function returns
           a loss per batch element instead and ignores size_average.
           Default: ``True``

        ignore_index (int, optional): Specifies a target value that is ignored
            and does not contribute to the input gradient. When size_average is
            ``True``, the loss is averaged over non-ignored targets.

    References:
        [1] https://github.com/kuangliu/pytorch-retinanet/blob/master/loss.py
        [2] https://arxiv.org/abs/1708.02002

    SeeAlso:
        https://github.com/marvis/pytorch-yolo2/blob/master/FocalLoss.py
        https://discuss.pytorch.org/t/how-to-implement-focal-loss-in-pytorch/6469/11

    Example:
        >>> self = FocalLoss(reduction='none')
        >>> # input is of size N x C
        >>> N, C = 8, 5
        >>> data = torch.randn(N, C, requires_grad=True)
        >>> # each element in target has to have 0 <= value < C
        >>> target = (torch.rand(N) * C).long()
        >>> input = torch.nn.LogSoftmax(dim=1)(data)
        >>> #self.focal_loss_alt(input, target)
        >>> self.focal_loss(input, target)
        >>> output = self(input, target)
        >>> output.sum().backward()

        input = torch.FloatTensor([
            [0, 1, 0, 0],
            [0, .9, 0, 0],
            [0, .98, 0, 0],
            [.7, .21, .1, .1],
            [.3, .3, .3, .1],
            [0, 1, 0, 0],
            [0, .9, 0, 0],
            [0, .98, 0, 0],
            [.7, .21, .1, .1],
            [.3, .3, .3, .1],
        ]) * 10
        target = torch.LongTensor([1, 1, 1, 1, 1, 0, 2, 3, 3, 3])

        weight = torch.FloatTensor([1, 1, 1, 10])
        self = FocalLoss(reduce=False, weight=weight)
    """

    def __init__(self, focus=2, weight=None, size_average=None, reduce=None,
                 reduction=ELEMENTWISE_MEAN, ignore_index=-100):
        size_average, reduce, reduction = _backwards_compat_reduction_kw(
            size_average, reduce, reduction)
        super(FocalLoss, self).__init__(weight=weight, reduction=reduction)
        self.focus = focus
        self.ignore_index = ignore_index

    def focal_loss(self, input, target):
        """
        Focal loss standard definition.

        Args:
          input: (tensor) sized [N,D].
          target: (tensor) sized [N,].

        Return:
          (tensor) sized [N,] focal loss for each class

        CommandLine:
            python -m netharn.loss FocalLoss.focal_loss:0 --profile
            python -m netharn.loss FocalLoss.focal_loss:1 --profile

        Example:
            >>> # input is of size N x C
            >>> import numpy as np
            >>> N, C = 8, 5
            >>> # each element in target has to have 0 <= value < C
            >>> target = (torch.rand(N) * C).long()
            >>> input = torch.randn(N, C, requires_grad=True)
            >>> # Check to be sure that when gamma=0, FL becomes CE
            >>> loss0 = FocalLoss(reduction='none', focus=0).focal_loss(input, target)
            >>> loss1 = F.cross_entropy(input, target, reduction='none')
            >>> #loss1 = F.cross_entropy(input, target, size_average=False, reduce=False)
            >>> loss2 = F.nll_loss(F.log_softmax(input, dim=1), target, reduction='none')
            >>> #loss2 = F.nll_loss(F.log_softmax(input, dim=1), target, size_average=False, reduce=False)
            >>> assert np.all(np.abs((loss1 - loss0).data.numpy()) < 1e-6)
            >>> assert np.all(np.abs((loss2 - loss0).data.numpy()) < 1e-6)
            >>> lossF = FocalLoss(reduction='none', focus=2, ignore_index=0).focal_loss(input, target)
            >>> weight = torch.rand(C)
            >>> lossF = FocalLoss(reduction='none', focus=2, weight=weight, ignore_index=0).focal_loss(input, target)
        """
        if True:
            return self.nll_focal_loss(
                input, target, focus=self.focus, dim=self.dim,
                weight=self.weight, ignore_index=self.ignore_index,
                reduction=self.reduction)
        else:
            if self.weight is None:
                alpha = 1
            else:
                # Create a per-input weight
                alpha = self.weight[target]
                # alpha = autograd.Variable(self.weight)[target]

            # Compute log(p) for NLL-loss.
            nll = F.log_softmax(input, dim=1)  # [N,C]

            gamma = self.focus

            num_classes = input.shape[1]

            # remove any loss associated with ignore_label
            mask = (target != self.ignore_index).float()  # [N,]

            # Determine which entry in nll corresponds to the target
            t = kwarray.one_hot_embedding(target.data, num_classes)  # [N,C]
            # t = autograd.Variable(t)

            # We only need the log(p) component corresponding to the target class
            target_nll = (nll * t).sum(dim=1)  # [N,]  # sameas nll[t > 0]
            target_p = torch.exp(target_nll)   # [N,]

            # Reduce the weight of easy examples
            hardness = (1 - target_p)               # [N,]
            w = alpha * hardness.pow(gamma)  # [N,]

            # Normal cross-entropy computation (but with augmented weights per example)
            output = -w * mask * target_nll  # [N,]
            return output

    def forward(self, input, target):
        """
        Args:
          input: (tensor) predicted class confidences, sized [batch_size, #classes].
          target: (tensor) encoded target labels, sized [batch_size].

        Returns:
            (tensor) loss
        """
        output = self.focal_loss(input, target)
        if self.reduction == ELEMENTWISE_MEAN:
            output = output.mean()
        elif self.reduction == 'sum':
            output = output.sum()
        return output


if __name__ == '__main__':
    """
    CommandLine:
        xdoctest -m netharn.criterions.focal all
    """
    import xdoctest
    xdoctest.doctest_module(__file__)
