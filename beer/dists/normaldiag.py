import abc
from dataclasses import dataclass
import math
import torch
from .basedist import ExponentialFamily
from .basedist import ConjugateLikelihood


__all__ = ['NormalDiagonalCovariance', 'NormalDiagonalCovarianceStdParams',
           'NormalFixedDiagonalCovarianceLikelihood']

@dataclass
class NormalFixedDiagonalCovarianceLikelihood(ConjugateLikelihood):
    dim: int

    @property
    def sufficient_statistics_dim(self, zero_stats=True):
        zero_stats_dim = self.dim if zero_stats else 0
        return self.dim + zero_stats_dim
    
    @staticmethod
    def sufficient_statistics(data):
        dim = data.shape[-1]
        length = len(data)
        tensorconf = {'dtype': data.dtype, 'device': data.device,
                      'requires_grad': False}
        return torch.cat([
            data,
            -.5 * torch.ones_like(data, requires_grad=False),
        ], dim=-1)

    def parameters_from_pdfvector(self, pdfvec):
        return pdfvec[:self.dim]

    def pdfvectors_from_rvectors(self, rvecs):
        return torch.cat([rvecs, rvecs**2], dim=-1)

    def __call__(self, pdfvecs, stats):
        if len(pdfvecs.shape) == 1:
            pdfvecs = pdfvecs.view(1, -1)
        log_basemeasure = -.5 * self.dim * math.log(2 * math.pi)
        return stats @ pdfvecs.t() + log_basemeasure


@dataclass(init=False, eq=False, unsafe_hash=True)
class NormalDiagonalCovarianceStdParams(torch.nn.Module):
    '''Standard parameterization of the Normal pdf with diagonal 
    covariance matrix.
    '''

    mean: torch.Tensor
    diag_cov: torch.Tensor

    def __init__(self, mean, diag_cov):
        super().__init__()
        self.register_buffer('mean', mean)
        self.register_buffer('diag_cov', diag_cov)

    @classmethod
    def from_natural_parameters(cls, natural_params):
        dim = (len(natural_params)) // 2
        np1 = natural_params[:dim]
        np2 = natural_params[dim:2 * dim]
        diag_cov = 1. / (-2 * np2)
        mean = diag_cov * np1
        return cls(mean, diag_cov)


class NormalDiagonalCovariance(ExponentialFamily):
    'Normal pdf with diagonal covariance matrix.'

    _std_params_def = {
        'mean': 'Mean parameter.',
        'diag_cov': 'Diagonal of the covariance matrix.',
    }

    def __len__(self):
        paramshape = self.params.mean.shape
        return 1 if len(paramshape) <= 1 else paramshape[0]

    @property
    def dim(self):
        return len(self.params.mean)

    def conjugate(self):
        return NormalFixedDiagonalCovarianceLikelihood(self.dim)

    def forward(self, data):
        nparams = self.natural_parameters()
        stats = torch.cat([data, data**2], dim=-1)
        return stats @ nparams - .5 * self.dim * math.log(2 * math.pi)

    def expected_sufficient_statistics(self):
        '''Expected sufficient statistics given the current
        parameterization.

        For the random variable x (vector)the sufficient statistics of 
        the Normal with diagonal covariance matrix are given by:

        stats = (
            x,
            x**2,
        )

        For the standard parameters (m=mean, s=diagonal of the cov. 
        matrix) the expectation of the sufficient statistics is
        given by:

        E[stats] = (
            m,
            s + m**2
        )

        '''
        return torch.cat([
            self.params.mean,
            self.params.diag_cov + self.params.mean ** 2
        ])

    def expected_value(self):
        return self.params.mean

    def log_norm(self):
        dim = self.dim
        mean = self.params.mean
        diag_prec = 1./ self.params.diag_cov
        log_base_measure = -.5 * dim * math.log(2 * math.pi)
        return -.5 * (diag_prec * mean) @ mean \
                + .5 * diag_prec.log().sum() \
                + log_base_measure

    def sample(self, nsamples):
        mean = self.params.mean
        diag_cov = self.params.diag_cov
        noise = torch.randn(nsamples, self.dim, dtype=mean.dtype, 
                            device=mean.device)
        return mean[None] + diag_cov[None] * noise

    def natural_parameters(self):
        '''Natural form of the current parameterization. For the
        standard parameters (m=mean, s=diagonal of the cov. matrix) the
        natural parameterization is given by:

        nparams = (
            s^-1 * m ,
            -.5 * s^1
        )

        Returns:
            ``torch.Tensor[2 * D]``

        '''
        mean = self.params.mean
        diag_prec = 1. / self.params.diag_cov
        return torch.cat([diag_prec * mean, -.5 * diag_prec])

    def update_from_natural_parameters(self, natural_params):
        self.params = self.params.from_natural_parameters(natural_params)
