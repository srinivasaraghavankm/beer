'Tests for the subspace models.'

# pylint: disable=C0413
# Not all the modules can be placed at the top of the files as we need
# first to change the PYTHONPATH before to import the modules.
import sys
sys.path.insert(0, './')
sys.path.insert(0, './tests')

import math
import unittest
import numpy as np
import torch
import beer
from basetest import BaseTest

from beer.expfamilyprior import _matrixnormal_fc_split_nparams


########################################################################
# PPCA.
########################################################################

# pylint: disable=R0902
class TestPPCA(BaseTest):

    def setUp(self):
        self.dim = int(1 + torch.randint(100, (1, 1)).item())
        self.npoints = int(1 + torch.randint(100, (1, 1)).item())
        self.data = torch.randn(self.npoints, self.dim).type(self.type)
        self.means = torch.randn(self.npoints, self.dim).type(self.type)
        self.vars = torch.randn(self.npoints, self.dim).type(self.type) ** 2
        self.mean = torch.randn(self.dim).type(self.type)
        self.prec = 1 + (torch.randn(self.dim)**2).type(self.type)
        self.prior_count = 1e-2 + 100 * torch.rand(1).item()

        # Prior/Posterior mean.
        mean = torch.randn(self.dim).type(self.type)
        var = (1 + torch.randn(1)**2).type(self.type)
        self.prior_mean = beer.NormalIsotropicCovariancePrior(mean,var)
        self.global_mean = torch.randn(self.dim).type(self.type)
        self.global_var = (1 + torch.randn(1)**2).type(self.type)
        self.posterior_mean = beer.NormalIsotropicCovariancePrior(
            self.global_mean,
            self.global_var
        )

        # Prior/Posterior precision.
        shape = (1 + torch.randn(1) ** 2).type(self.type)
        rate = (1 + torch.randn(1) ** 2).type(self.type)
        self.prior_prec = beer.GammaPrior(shape, rate)
        self.shape = (1 + torch.randn(1) ** 2).type(self.type)
        self.rate = (1 + torch.randn(1) ** 2).type(self.type)
        self.posterior_prec = beer.GammaPrior(self.shape, self.rate)

        # Prior/Posterior subspace.
        self.dim_subspace = int(1 + torch.randint(100, (1, 1)).item())
        mean = torch.randn(self.dim_subspace, self.dim).type(self.type)
        cov = (1 + torch.randn(self.dim_subspace)).type(self.type)
        cov = torch.eye(self.dim_subspace).type(self.type) + torch.ger(cov, cov)
        self.prior_subspace = beer.MatrixNormalPrior(mean, cov)
        self.mean_subspace = torch.randn(self.dim_subspace, self.dim).type(self.type)
        cov = (1 + torch.randn(self.dim_subspace)).type(self.type)
        self.cov_subspace = torch.eye(self.dim_subspace).type(self.type) + torch.ger(cov, cov)
        self.posterior_subspace = beer.MatrixNormalPrior(self.mean_subspace,
                                                         self.cov_subspace)

    def test_create(self):
        model = beer.PPCA(
            self.prior_prec, self.posterior_prec,
            self.prior_mean, self.posterior_mean,
            self.prior_subspace, self.posterior_subspace,
            self.dim_subspace
        )
        self.assertAlmostEqual(float(model.precision),
                               float(self.shape / self.rate))
        self.assertArraysAlmostEqual(model.mean.numpy(), self.global_mean)
        self.assertArraysAlmostEqual(model.subspace.numpy(), self.mean_subspace)

    def test_sufficient_statistics(self):
        data = self.data.numpy()
        stats1 = np.c_[np.sum(data ** 2, axis=1), self.data, \
                       np.ones(len(data))]
        stats2 = beer.PPCA.sufficient_statistics(self.data)
        self.assertArraysAlmostEqual(stats1, stats2.numpy())

    def test_sufficient_statistics_from_mean_var(self):
        stats1 = beer.PPCA.sufficient_statistics_from_mean_var(self.means,
                                                               self.vars)
        means, variances = self.means.numpy(), self.vars.numpy()
        stats2 = np.c_[np.sum(means ** 2 + variances, axis=1), means,
                       np.ones(len(means))]
        self.assertArraysAlmostEqual(stats1.numpy(), stats2)

    def test_latent_posterior(self):
        model = beer.PPCA(
            self.prior_prec, self.posterior_prec,
            self.prior_mean, self.posterior_mean,
            self.prior_subspace, self.posterior_subspace,
            self.dim_subspace
        )
        stats = model.sufficient_statistics(self.data)
        data = stats[:, 1:-1].numpy()
        s_cov, s_mean =  _matrixnormal_fc_split_nparams(
            model._subspace_param.expected_value,
            model._subspace_dim,
            model._data_dim
        )
        s_cov, s_mean = s_cov.numpy(), s_mean.numpy()
        prec = model.precision.numpy()
        cov1 = np.linalg.inv(np.eye(self.dim_subspace) + prec * s_cov)
        means1 = prec * cov1 @ s_mean @ (data - model.mean.numpy()).T
        means2, cov2 = model.latent_posterior(stats)
        self.assertArraysAlmostEqual(cov1, cov2.numpy())
        self.assertArraysAlmostEqual(means1, means2.numpy())

    @unittest.skip("Not implemented")
    def test_forward(self):
        model = beer.PPCA(
            self.prior_prec, self.posterior_prec,
            self.prior_mean, self.posterior_mean,
            self.prior_subspace, self.posterior_subspace,
            self.dim_subspace
        )
        stats = model.sufficient_statistics(self.data)
        means, cov = model.latent_posterior(stats)
        nparams = model.parameters[0].expected_value
        exp_llh1 = stats @ nparams
        exp_llh1 -= .5 * self.data.size(1) * math.log(2 * math.pi)
        exp_llh2 = model(stats)
        self.assertArraysAlmostEqual(exp_llh1.numpy(), exp_llh2.numpy())

    @unittest.skip("Not implemented")
    def test_expected_natural_params(self):
        model = beer.NormalDiagonalCovariance(
            NormalGammaPrior(self.mean, self.prec, self.prior_count),
            NormalGammaPrior(self.mean, self.prec, self.prior_count)
        )
        np1 = model.expected_natural_params(self.means, self.vars).numpy()
        np2 = model.parameters[0].expected_value.numpy()
        np2 = np.ones((self.means.size(0), len(np2))) * np2
        self.assertArraysAlmostEqual(np1, np2)


__all__ = ['TestPPCA']