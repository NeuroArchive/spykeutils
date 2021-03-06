import copy
import quantities as pq
import scipy as sp
import scipy.signal
import scipy.special
import tools

default_kernel_area_fraction = 0.99999


class Kernel(object):
    """ Base class for kernels.  """

    def __init__(self, kernel_size, normalize):
        """
        :param kernel_size: Parameter controlling the kernel size.
        :type kernel_size: Quantity 1D
        :param bool normalize: Whether to normalize the kernel to unit area.
        """
        self.kernel_size = kernel_size
        self.normalize = normalize

    def __call__(self, t, kernel_size=None):
        """ Evaluates the kernel at all time points in the array `t`.

        :param t: Time points to evaluate the kernel at.
        :type t: Quantity 1D
        :param kernel_size: If not `None` this overwrites the kernel size of
            the `Kernel` instance.
        :type kernel_size: Quantity scalar
        :returns: The result of the kernel evaluations.
        :rtype: Quantity 1D
        """

        if kernel_size is None:
            kernel_size = self.kernel_size

        if self.normalize:
            normalization = self.normalization_factor(kernel_size)
        else:
            normalization = 1.0 * pq.dimensionless

        return self._evaluate(t, kernel_size) * normalization

    def _evaluate(self, t, kernel_size):
        """ Evaluates the kernel.

        :param t: Time points to evaluate the kernel at.
        :type t: Quantity 1D
        :param kernel_size: Controls the width of the kernel.
        :type kernel_size: Quantity scalar
        :returns: The result of the kernel evaluations.
        :rtype: Quantity 1D
        """
        raise NotImplementedError()

    def normalization_factor(self, kernel_size):
        """ Returns the factor needed to normalize the kernel to unit area.

        :param kernel_size: Controls the width of the kernel.
        :type kernel_size: Quantity scalar
        :returns: Factor to normalize the kernel to unit width.
        :rtype: Quantity scalar
        """
        raise NotImplementedError()

    def boundary_enclosing_at_least(self, fraction):
        """ Calculates the boundary :math:`b` so that the integral from
        :math:`-b` to :math:`b` encloses at least a certain fraction of the
        integral over the complete kernel.

        :param float fraction: Fraction of the whole area which at least has to
            be enclosed.
        :returns: boundary
        :rtype: Quantity scalar
        """
        raise NotImplementedError()

    def is_symmetric(self):
        """ Should return `True` if the kernel is symmetric. """
        return False

    def summed_dist_matrix(self, vectors, presorted=False):
        """ Calculates the sum of all element pair distances for each
        pair of vectors.

        If :math:`(a_1, \\dots, a_n)` and :math:`(b_1, \\dots, b_m)` are the
        :math:`u`-th and :math:`v`-th vector from `vectors` and :math:`K` the
        kernel, the resulting entry in the 2D array will be :math:`D_{uv}
        = \\sum_{i=1}^{n} \\sum_{j=1}^{m} K(a_i - b_j)`.

        :param sequence vectors: A sequence of Quantity 1D to calculate the
            summed distances for each pair. The required units depend on the
            kernel. Usually it will be the inverse unit of the kernel size.
        :param bool presorted: Some optimized specializations of this function
            may need sorted vectors. Set `presorted` to `True` if you know that
            the passed vectors are already sorted to skip the sorting and thus
            increase performance.
        :rtype: Quantity 2D
        """

        D = sp.empty((len(vectors), len(vectors)))
        if len(vectors) > 0:
            might_have_units = self(vectors[0])
            if hasattr(might_have_units, 'units'):
                D = D * might_have_units.units
            else:
                D = D * pq.dimensionless

        for i, j in sp.ndindex(len(vectors), len(vectors)):
            D[i, j] = sp.sum(self(
                (vectors[i] - sp.atleast_2d(vectors[j]).T).flatten()))
        return D


class KernelFromFunction(Kernel):
    """ Creates a kernel form a function. Please note, that not all methods for
    such a kernel are implemented.
    """

    def __init__(self, kernel_func, kernel_size):
        Kernel.__init__(self, kernel_size, normalize=False)
        self._evaluate = kernel_func

    def is_symmetric(self):
        return False


def as_kernel_of_size(obj, kernel_size):
    """ Returns a kernel of desired size.

    :param obj: Either an existing kernel or a kernel function. A kernel
        function takes two arguments. First a `Quantity 1D` of evaluation time
        points and second a kernel size.
    :type obj: Kernel or func
    :param kernel_size: Desired size of the kernel.
    :type kernel_size: Quantity 1D
    :returns: A :class:`Kernel` with the desired kernel size. If `obj` is
        already a :class:`Kernel` instance, a shallow copy of this instance with
        changed kernel size will be returned. If `obj` is a function it will be
        wrapped in a :class:`Kernel` instance.
    :rtype: :class:`Kernel`
    """

    if isinstance(obj, Kernel):
        obj = copy.copy(obj)
        obj.kernel_size = kernel_size
    else:
        obj = KernelFromFunction(obj, kernel_size)
    return obj


class SymmetricKernel(Kernel):
    """ Base class for symmetric kernels. """

    def __init__(self, kernel_size, normalize):
        """
        :param kernel_size: Parameter controlling the kernel size.
        :type kernel_size: Quantity 1D
        :param bool normalize: Whether to normalize the kernel to unit area.
        """
        Kernel.__init__(self, kernel_size, normalize)

    def is_symmetric(self):
        return True

    def summed_dist_matrix(self, vectors, presorted=False):
        D = sp.empty((len(vectors), len(vectors)))
        if len(vectors) > 0:
            might_have_units = self(vectors[0])
            if hasattr(might_have_units, 'units'):
                D = D * might_have_units.units

        for i in xrange(len(vectors)):
            for j in xrange(i, len(vectors)):
                D[i, j] = D[j, i] = sp.sum(self(
                    (vectors[i] - sp.atleast_2d(vectors[j]).T).flatten()))
        return D


class CausalDecayingExpKernel(Kernel):
    r""" Unnormalized: :math:`K(t) = \exp(-\frac{t}{\tau}) \Theta(t)` with
    :math:`\Theta(t) = \left\{\begin{array}{ll}0, & x < 0\\ 1, & x \geq
    0\end{array}\right.` and kernel size :math:`\tau`.

    Normalized to unit area: :math:`K'(t) = \frac{1}{\tau} K(t)`
    """

    @staticmethod
    def evaluate(t, kernel_size):
        return sp.piecewise(
            t, [t < 0, t >= 0], [
                lambda t: 0,
                lambda t: sp.exp(
                    (-t * pq.dimensionless / kernel_size).simplified)])

    def _evaluate(self, t, kernel_size):
        return self.evaluate(t, kernel_size)

    def normalization_factor(self, kernel_size):
        return 1.0 / kernel_size

    def __init__(self, kernel_size=1.0 * pq.s, normalize=True):
        Kernel.__init__(self, kernel_size, normalize)

    def boundary_enclosing_at_least(self, fraction):
        return -self.kernel_size * sp.log(1.0 - fraction)


class GaussianKernel(SymmetricKernel):
    r""" Unnormalized: :math:`K(t) = \exp(-\frac{t^2}{2 \sigma^2})` with kernel
    size :math:`\sigma` (corresponds to the standard deviation of a Gaussian
    distribution).

    Normalized to unit area: :math:`K'(t) = \frac{1}{\sigma \sqrt{2 \pi}} K(t)`
    """

    @staticmethod
    def evaluate(t, kernel_size):
        return sp.exp(
            -0.5 * (t * pq.dimensionless / kernel_size).simplified ** 2)

    def _evaluate(self, t, kernel_size):
        return self.evaluate(t, kernel_size)

    def normalization_factor(self, kernel_size):
        return 1.0 / (sp.sqrt(2.0 * sp.pi) * kernel_size)

    def __init__(self, kernel_size=1.0 * pq.s, normalize=True):
        Kernel.__init__(self, kernel_size, normalize)

    def boundary_enclosing_at_least(self, fraction):
        return self.kernel_size * sp.sqrt(2.0) * \
            scipy.special.erfinv(fraction + scipy.special.erf(0.0))


class LaplacianKernel(SymmetricKernel):
    r""" Unnormalized: :math:`K(t) = \exp(-|\frac{t}{\tau}|)` with kernel size
    :math:`\tau`.

    Normalized to unit area: :math:`K'(t) = \frac{1}{2 \tau} K(t)`
    """

    @staticmethod
    def evaluate(t, kernel_size):
        return sp.exp(
            -(sp.absolute(t) * pq.dimensionless / kernel_size).simplified)

    def _evaluate(self, t, kernel_size):
        return self.evaluate(t, kernel_size)

    def normalization_factor(self, kernel_size):
        return 0.5 / kernel_size

    def __init__(self, kernel_size=1.0 * pq.s, normalize=True):
        Kernel.__init__(self, kernel_size, normalize)

    def boundary_enclosing_at_least(self, fraction):
        return -self.kernel_size * sp.log(1.0 - fraction)

    def summed_dist_matrix(self, vectors, presorted=False):
        # This implementation is based on
        #
        # Houghton, C., & Kreuz, T. (2012). On the efficient calculation of van
        # Rossum distances. Network: Computation in Neural Systems, 23(1-2),
        # 48-58.
        #
        # Note that the cited paper contains some errors: In formula (9) the
        # left side of the equation should be divided by two and in the last
        # sum in this equation it should say `j|v_i >= u_i` instead of
        # `j|v_i > u_i`. Also, in equation (11) it should say `j|u_i >= v_i`
        # instead of `j|u_i > v_i`.
        #
        # Given N vectors with n entries on average the run-time complexity is
        # O(N^2 * n). O(N^2 + N * n) memory will be needed.

        if len(vectors) <= 0:
            return sp.zeros((0, 0))

        if not presorted:
            vectors = [v.copy() for v in vectors]
            for v in vectors:
                v.sort()

        sizes = sp.asarray([v.size for v in vectors])
        values = sp.empty((len(vectors), max(1, sizes.max())))
        values.fill(sp.nan)
        for i, v in enumerate(vectors):
            if v.size > 0:
                values[i, :v.size] = \
                    (v / self.kernel_size * pq.dimensionless).simplified

        exp_diffs = sp.exp(values[:, :-1] - values[:, 1:])
        markage = sp.zeros(values.shape)
        for u in xrange(len(vectors)):
            markage[u, 0] = 0
            for i in xrange(sizes[u] - 1):
                markage[u, i + 1] = (markage[u, i] + 1.0) * exp_diffs[u, i]

        # Same vector terms
        D = sp.empty((len(vectors), len(vectors)))
        D[sp.diag_indices_from(D)] = sizes + 2.0 * sp.sum(markage, axis=1)

        # Cross vector terms
        for u in xrange(D.shape[0]):
            all_ks = sp.searchsorted(values[u], values, 'left') - 1
            for v in xrange(u):
                js = sp.searchsorted(values[v], values[u], 'right') - 1
                ks = all_ks[v]
                slice_j = sp.s_[sp.searchsorted(js, 0):sizes[u]]
                slice_k = sp.s_[sp.searchsorted(ks, 0):sizes[v]]
                D[u, v] = sp.sum(
                    sp.exp(values[v][js[slice_j]] - values[u][slice_j]) *
                    (1.0 + markage[v][js[slice_j]]))
                D[u, v] += sp.sum(
                    sp.exp(values[u][ks[slice_k]] - values[v][slice_k]) *
                    (1.0 + markage[u][ks[slice_k]]))
                D[v, u] = D[u, v]

        if self.normalize:
            normalization = self.normalization_factor(self.kernel_size)
        else:
            normalization = 1.0
        return normalization * D


class RectangularKernel(SymmetricKernel):
    r""" Unnormalized: :math:`K(t) = \left\{\begin{array}{ll}1, & |t| < \tau \\
    0, & |t| \geq \tau\end{array} \right.` with kernel size :math:`\tau`
    corresponding to the half width.

    Normalized to unit area: :math:`K'(t) = \frac{1}{2 \tau} K(t)`
    """

    @staticmethod
    def evaluate(t, half_width):
        return sp.absolute(t) < half_width

    def _evaluate(self, t, kernel_size):
        return self.evaluate(t, kernel_size)

    def normalization_factor(self, half_width):
        return 0.5 / half_width

    def __init__(self, half_width=1.0 * pq.s, normalize=True):
        Kernel.__init__(self, half_width, normalize)

    def boundary_enclosing_at_least(self, fraction):
        return self.kernel_size


class TriangularKernel(SymmetricKernel):
    r""" Unnormalized: :math:`K(t) = \left\{ \begin{array}{ll}1
    - \frac{|t|}{\tau}, & |t| < \tau \\ 0, & |t| \geq \tau \end{array} \right.`
    with kernel size :math:`\tau` corresponding to the half width.

    Normalized to unit area: :math:`K'(t) = \frac{1}{\tau} K(t)`
    """

    @staticmethod
    def evaluate(t, half_width):
        return sp.maximum(
            0.0,
            (1.0 - sp.absolute(t.rescale(half_width.units)) * pq.dimensionless /
             half_width).magnitude)

    def _evaluate(self, t, kernel_size):
        return self.evaluate(t, kernel_size)

    def normalization_factor(self, half_width):
        return 1.0 / half_width

    def __init__(self, half_width=1.0 * pq.s, normalize=True):
        Kernel.__init__(self, half_width, normalize)

    def boundary_enclosing_at_least(self, fraction):
        return self.kernel_size


def discretize_kernel(
        kernel, sampling_rate, area_fraction=default_kernel_area_fraction,
        num_bins=None, ensure_unit_area=False):
    """ Discretizes a kernel.

    :param kernel: The kernel or kernel function. If a kernel function is used
        it should take exactly one 1-D array as argument.
    :type kernel: :class:`Kernel` or function
    :param float area_fraction: Fraction between 0 and 1 (exclusive)
        of the integral of the kernel which will be at least covered by the
        discretization. Will be ignored if `num_bins` is not `None`. If
        `area_fraction` is used, the kernel has to provide a method
        :meth:`boundary_enclosing_at_least` (see
        :meth:`.Kernel.boundary_enclosing_at_least`).
    :param sampling_rate: Sampling rate for the discretization. The unit will
        typically be a frequency unit.
    :type sampling_rate: Quantity scalar
    :param int num_bins: Number of bins to use for the discretization.
    :param bool ensure_unit_area: If `True`, the area of the discretized
        kernel will be normalized to 1.0.
    :rtype: Quantity 1D
    """

    t_step = 1.0 / sampling_rate

    if num_bins is not None:
        start = -num_bins // 2
        stop = num_bins // 2
    elif area_fraction is not None:
        boundary = kernel.boundary_enclosing_at_least(area_fraction)
        if hasattr(boundary, 'rescale'):
            boundary = boundary.rescale(t_step.units)
        start = sp.ceil(-boundary / t_step)
        stop = sp.floor(boundary / t_step) + 1
    else:
        raise ValueError(
            "One of area_fraction and num_bins must not be None.")

    k = kernel(sp.arange(start, stop) * t_step)
    if ensure_unit_area:
        k /= sp.sum(k) * t_step
    return k


def smooth(
        binned, kernel, sampling_rate, mode='same',
        **kernel_discretization_params):
    """ Smoothes a binned representation (e.g. of a spike train) by convolving
    with a kernel.

    :param binned: Bin array to smooth.
    :type binned: 1-D array
    :param kernel: The kernel instance to convolve with.
    :type kernel: :class:`Kernel`
    :param sampling_rate: The sampling rate which will be used to discretize the
        kernel. It should be equal to the sampling rate used to obtain `binned`.
        The unit will typically be a frequency unit.
    :type sampling_rate: Quantity scalar
    :param mode:
        * 'same': The default which returns an array of the same size as
          `binned`
        * 'full': Returns an array with a bin for each shift where `binned` and
          the discretized kernel overlap by at least one bin.
        * 'valid': Returns only the discretization bins where the discretized
          kernel and `binned` completely overlap.

        See also `numpy.convolve
        <http://docs.scipy.org/doc/numpy/reference/generated/numpy.convolve.html>`_.
    :type mode: {'same', 'full', 'valid'}
    :param dict kernel_discretization_params: Additional discretization
        arguments which will be passed to :func:`.discretize_kernel`.
    :returns: The smoothed representation of `binned`.
    :rtype: Quantity 1D
    """
    k = discretize_kernel(
        kernel, sampling_rate=sampling_rate, **kernel_discretization_params)
    return scipy.signal.convolve(binned, k, mode) * k.units


def st_convolve(
        train, kernel, sampling_rate, mode='same', binning_params=None,
        kernel_discretization_params=None):
    """ Convolves a :class:`neo.core.SpikeTrain` with a kernel.

    :param train: Spike train to convolve.
    :type train: :class:`neo.core.SpikeTrain`
    :param kernel: The kernel instance to convolve with.
    :type kernel: :class:`Kernel`
    :param sampling_rate: The sampling rate which will be used to bin
        the spike train. The unit will typically be a frequency unit.
    :type sampling_rate: Quantity scalar
    :param mode:
        * 'same': The default which returns an array covering the whole
          duration of the spike train `train`.
        * 'full': Returns an array with additional discretization bins in the
          beginning and end so that for each spike the whole discretized
          kernel is included.
        * 'valid': Returns only the discretization bins where the discretized
          kernel and spike train completely overlap.

        See also :func:`scipy.signal.convolve`.
    :type mode: {'same', 'full', 'valid'}
    :param dict binning_params: Additional discretization arguments which will
        be passed to :func:`.tools.bin_spike_trains`.
    :param dict kernel_discretization_params: Additional discretization
        arguments which will be passed to :func:`.discretize_kernel`.
    :returns: The convolved spike train, the boundaries of the discretization
        bins
    :rtype: (Quantity 1D, Quantity 1D with the inverse units of `sampling_rate`)
    """
    if binning_params is None:
        binning_params = {}
    if kernel_discretization_params is None:
        kernel_discretization_params = {}

    binned, bins = tools.bin_spike_trains(
        {0: [train]}, sampling_rate, **binning_params)
    binned = binned[0][0]
    #sampling_rate = binned.size / (bins[-1] - bins[0])
    result = smooth(
        binned, kernel, sampling_rate, mode, **kernel_discretization_params)

    assert (result.size - binned.size) % 2 == 0
    num_additional_bins = (result.size - binned.size) // 2

    if len(binned):
        bins = sp.linspace(
            bins[0] - num_additional_bins / sampling_rate,
            bins[-1] + num_additional_bins / sampling_rate,
            result.size + 1)
    else:
        bins = [] * pq.s

    return result, bins
