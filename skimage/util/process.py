__all__ = ['process_blocks', 'FuncExec']

import numpy as np
from skimage.util import view_as_windows
from multiprocessing import Pool, Manager
from Queue import Queue
from functools import partial

def _exec(func, queue, index_and_view=(True,False), **kwargs):
    """A simple wrapper function to put the result from a function operating
    on a view of an np.ndarray into a result queue. Needed to overcome
    limitations with regards to mapping of a class method using
    multiprocessing.pool.map. Also multiprocessing.pool.map does not allow
    for multiple iterable arguments, so index_and_view is a workaround. 
    """
    index, view = index_and_view
    result = func(view, **kwargs)
    queue.put((index,result))

class FuncExec(object):
    """FuncExec is a function execution helper class.
    It is a base class that allows for synchronous execution of a function
    that operates on views that was typically returned from the
    view_as_windows or view_as_blocks functions.
    """
    def __init__(self, func, func_args={}):
        self.func = func
        self.func_args = func_args
        self.queue = Queue()
        self.out_shape = None
        self.views = None

    def __call__(self, views, dims=None):
        if dims is None:
            dims = len(views.shape)/2
        elif dims > len(views.shape):
            raise ValueError("Parameter 'dims' must not be larger than\
                    the number of dimensions of the 'views' parameter.")
        self.views = views
        self.out_shape = self.views.shape[:dims]
        self._map(np.ndindex(*self.out_shape), )
        return self

    def _map(self, indices):
        map_func = partial(_exec, self.func, self.queue, **self.func_args)
        map(map_func, [(index, self.views[index]) for index in indices])

    #def _exec(self, index):
    #    result = self.func(self.views[index], **self.func_args)
    #    self._callback(index, result)

    def ready(self, timeout=None):
        count = 0
        while count < np.prod(self.out_shape):
            idx, value = self.queue.get(True, timeout)
            if isinstance(value, np.ndarray):
                yield idx, value.astype(None)
            else:
                yield idx, value
            count += 1

    def result(self, timeout=None):
        result = np.zeros(self.out_shape).astype(np.object)
        for idx, value in self.ready(timeout):
            result[idx] = value
        return np.array(result.tolist())

class MultiProcExec(FuncExec):
    """MultiProcExec is a function execution helper class.
    It allows for multiprocess execution of a function
    that operates on views that was typically returned from the
    view_as_windows or view_as_blocks functions.
    """
    def __init__(self, func, func_args={}, pool_size=2):
        super(MultiProcExec, self).__init__(func, func_args=func_args)
        self.manager = Manager()
        self.queue = self.manager.Queue()
        self.pool = Pool(processes=pool_size)

    def _map(self, indices):
        map_func = partial(_exec, self.func, self.queue, **self.func_args)
        results = self.pool.map(map_func, [(index, self.views[index]) for index in indices])

def process_blocks(image, block_shape, func, func_args={},
                   overlap=0, executor=FuncExec, executor_args={}):
    """Apply a function to distinct or overlapping blocks in the image.

    Parameters
    ----------
    image : ndarray
        Input image.
    block_shape : tuple
        Block size.
    func : callable, f(
        Function to be applied to each window.
    func_args : dict
        Additional arguments for `func`.
    overlap : int
        The amount of overlap between blocks.
    executor : class
        Helper class that conforms to the default FuncExec class.
        Determines the execution plan (sync, multiprocess, etc).
    executor_args : dict
        Additional arguments for executor.__init__.

    Returns
    -------
    output : ndarray
        Outputs generated by applying the function to each block.

    Examples
    --------
    >>> from skimage.data import camera
    >>> image = camera()
    >>> output = process_blocks(image, (8, 8), np.sum)
    >>>
    >>> from skimage.color import gray2rgb
    >>> output2 = process_windows(gray2rgb(image), (8, 8, 3),
    ...                           np.sum, {'axis': -1})

    """
    block_shape = np.asarray(block_shape)
    step = max(block_shape) - overlap

    if block_shape.size != image.ndim:
        raise ValueError("Block shape must correspond to image dimensions")

    image_views = view_as_windows(image, block_shape, step)
    out_shape = image_views.shape[:-block_shape.size]

    execute = executor(func, func_args, **executor_args)
    return execute(image_views, len(out_shape))
