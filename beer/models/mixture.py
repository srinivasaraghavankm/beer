
"""Bayesian Mixture model."""

from itertools import chain
from .model import ConjugateExponentialModel
from ..priors import DirichletPrior
from scipy.special import logsumexp
import copy
import numpy as np


class Mixture(ConjugateExponentialModel):
    """Bayesian Mixture Model."""

    @staticmethod
    def create(n_components, create_component_func, args, prior_count=1):
        # Create the prior over the weights of the mixture.
        prior_weights = DirichletPrior.from_std_parameters(
            np.ones(n_components) * prior_count)

        # Create the components of the mixture.
        components = [create_component_func(**args)
                      for i in range(n_components)]

        return Mixture(prior_weights, components)

    def __init__(self, prior_weights, components, posterior_weights=None):
        """Initialize the Bayesian normal distribution.

        Args:
            prior_weights (``beer.priors.Dirichlet``): Prior over the
                weights of the mixture.
            components (list): List of components of the mixture.

        """
        # This will be initialize in the _prepare() call.
        self._np_params_matrix = None

        self.prior_weights = prior_weights
        self.components = components
        if posterior_weights is not None:
            self.posterior_weights = posterior_weights
        else:
            self.posterior_weights = copy.deepcopy(prior_weights)

        self._prepare()

    @property
    def weights(self):
        """Expected value of the weights."""
        return np.exp(self.posterior_weights.grad_lognorm(normalize=True))

    def sufficient_statistics(self, X):
        """Compute the sufficient statistics of the data.

        Args:
            X (numpy.ndarray): Data.

        Returns:
            (numpy.ndarray): Sufficient statistics of the data.

        """
        return np.c_[self.components[0].sufficient_statistics(X),
                     np.ones(X.shape[0])]

    def _prepare(self):
        matrix = np.vstack([component.posterior.grad_lognorm()
            for component in self.components])
        self._np_params_matrix = np.c_[matrix,
            self.posterior_weights.grad_lognorm()]

    def expected_natural_params(self, mean, var):
        '''Expected value of the natural parameters of the model given
        the sufficient statistics.

        '''
        T = self.components[0].sufficient_statistics_from_mean_var(mean, var)
        T2 = np.c_[T, np.ones(T.shape[0])]

        # Inference.
        per_component_exp_llh = T2 @ self._np_params_matrix.T
        exp_llh = logsumexp(per_component_exp_llh, axis=1)
        resps = np.exp(per_component_exp_llh - exp_llh[:, None])

        # Build the matrix of expected natural parameters.
        matrix = np.c_[[component.expected_natural_params(mean, var)[0][0]
                        for component in self.components]]

        # Accumulate the sufficient statistics.
        acc_stats = resps.T @ T2[:, :-1], resps.sum(axis=0)

        return (resps @ matrix), acc_stats


    def exp_llh(self, X, accumulate=False):
        """Expected value of the log-likelihood w.r.t to the posterior
        distribution over the parameters.

        Args:
            X (numpy.ndarray): Data as a matrix.
            accumulate (boolean): If True, returns the accumulated
                statistics.

        Returns:
            numpy.ndarray: Per-frame expected value of the
                log-likelihood.
            numpy.ndarray: Accumulated statistics (if ``accumulate=True``).

        """
        T = self.sufficient_statistics(X)

        # Note: the lognormalizer is already included in the expected
        # value of the natural parameters.
        per_component_exp_llh = T @ self._np_params_matrix.T

        # Components' responsibilities.
        exp_llh = logsumexp(per_component_exp_llh, axis=1)
        resps = np.exp(per_component_exp_llh - exp_llh[:, None])
        exp_llh -= .5 * X.shape[1] * np.log(2 * np.pi)

        if accumulate:
            acc_stats = resps.T @ T[:, :-1], resps.sum(axis=0)
            return exp_llh, acc_stats

        return exp_llh

    def kl_div_posterior_prior(self):
        """KL divergence between the posterior and prior distribution.

        Returns:
            float: KL divergence.

        """
        return self.posterior_weights.kl_div(self.prior_weights) + \
            np.sum([component.posterior.kl_div(component.prior)
                    for component in self.components])

    def natural_grad_update(self, acc_stats, scale, lrate):
        """Perform a natural gradient update of the posteriors'
        parameters.

        Args:
            acc_stats (dict): Accumulated statistics.
            scale (float): Scale of the sufficient statistics.
            lrate (float): Learning rate.

        """
        comp_stats, weights_stats = acc_stats

        # Update the components.
        for i, component in enumerate(self.components):
            # Compute the natural gradient.
            natural_grad = component.prior.natural_params \
                + scale * comp_stats[i] \
                - component.posterior.natural_params

            # Update the posterior distribution.
            component.posterior.natural_params += lrate * natural_grad

        # Update the weights.
        natural_grad = self.prior_weights.natural_params \
            + scale * weights_stats - self.posterior_weights.natural_params
        self.posterior_weights.natural_params += lrate * natural_grad

        self._prepare()

    def split(self):
        '''Split each component into two sub-components.

        Returns:
            (``Mixture``): A new mixture with two times more
                components.

        '''
        # Create the prior/posterior over the weights.
        prior_np = .5 * np.c_[self.prior_weights.natural_params,
                              self.prior_weights.natural_params].ravel()
        post_np = .5 * np.c_[self.posterior_weights.natural_params,
                             self.posterior_weights.natural_params].ravel()
        new_prior_weights = DirichletPrior(prior_np)
        new_posterior_weights = DirichletPrior(post_np)

        # Split the Normal distributions.
        new_components = [comp.split() for comp in self.components]
        new_components = list(chain.from_iterable(new_components))

        return Mixture(new_prior_weights, new_components,
                       new_posterior_weights)
