# Licensed under the Apache License: http://www.apache.org/licenses/LICENSE-2.0
# For details: https://github.com/nedbat/coveragepy/blob/master/NOTICE.txt

"""
.. versionadded:: 4.0

Plug-in interfaces for coverage.py.

Coverage.py supports a few different kinds of plug-ins that change its
behavior:

* File tracers implement tracing of non-Python file types.

* Configurers add custom configuration, using Python code to change the
  configuration.

* Dynamic context switchers decide when the dynamic context has changed, for
  example, to record what test function produced the coverage.

To write a coverage.py plug-in, create a module with a subclass of
:class:`~coverage.CoveragePlugin`.  You will override methods in your class to
participate in various aspects of coverage.py's processing.
Different types of plug-ins have to override different methods.

Any plug-in can optionally implement :meth:`~coverage.CoveragePlugin.sys_info`
to provide debugging information about their operation.

Your module must also contain a ``coverage_init`` function that registers an
instance of your plug-in class::

    import coverage

    class MyPlugin(coverage.CoveragePlugin):
        ...

    def coverage_init(reg, options) -> None:
        reg.add_file_tracer(MyPlugin())

You use the `reg` parameter passed to your ``coverage_init`` function to
register your plug-in object.  The registration method you call depends on
what kind of plug-in it is.

If your plug-in takes options, the `options` parameter is a dictionary of your
plug-in's options from the coverage.py configuration file.  Use them however
you want to configure your object before registering it.

Coverage.py will store its own information on your plug-in object, using
attributes whose names start with ``_coverage_``.  Don't be startled.

.. warning::
    Plug-ins are imported by coverage.py before it begins measuring code.
    If you write a plugin in your own project, it might import your product
    code before coverage.py can start measuring.  This can result in your
    own code being reported as missing.

    One solution is to put your plugins in your project tree, but not in
    your importable Python package.


.. _file_tracer_plugins:

File Tracers
============

File tracers implement measurement support for non-Python files.  File tracers
implement the :meth:`~coverage.CoveragePlugin.file_tracer` method to claim
files and the :meth:`~coverage.CoveragePlugin.file_reporter` method to report
on those files.

In your ``coverage_init`` function, use the ``add_file_tracer`` method to
register your file tracer.


.. _configurer_plugins:

Configurers
===========

.. versionadded:: 4.5

Configurers modify the configuration of coverage.py during start-up.
Configurers implement the :meth:`~coverage.CoveragePlugin.configure` method to
change the configuration.

In your ``coverage_init`` function, use the ``add_configurer`` method to
register your configurer.


.. _dynamic_context_plugins:

Dynamic Context Switchers
=========================

.. versionadded:: 5.0

Dynamic context switcher plugins implement the
:meth:`~coverage.CoveragePlugin.dynamic_context` method to dynamically compute
the context label for each measured frame.

Computed context labels are useful when you want to group measured data without
modifying the source code.

For example, you could write a plugin that checks `frame.f_code` to inspect
the currently executed method, and set the context label to a fully qualified
method name if it's an instance method of `unittest.TestCase` and the method
name starts with 'test'.  Such a plugin would provide basic coverage grouping
by test and could be used with test runners that have no built-in coveragepy
support.

In your ``coverage_init`` function, use the ``add_dynamic_context`` method to
register your dynamic context switcher.

"""

from __future__ import annotations
import functools
from types import FrameType
from typing import Sequence, Generator

from coverage import files
from coverage.config import CoverageConfig
from coverage.misc import contract, _needs_to_implement


class CoveragePlugin:
    """Base class for coverage.py plug-ins."""

    def file_tracer(self, filename: str) -> FileTracer:        # pylint: disable=unused-argument
        """Get a :class:`FileTracer` object for a file.

        Plug-in type: file tracer.

        Every Python source file is offered to your plug-in to give it a chance
        to take responsibility for tracing the file.  If your plug-in can
        handle the file, it should return a :class:`FileTracer` object.
        Otherwise return None.

        There is no way to register your plug-in for particular files.
        Instead, this method is invoked for all  files as they are executed,
        and the plug-in decides whether it can trace the file or not.
        Be prepared for `filename` to refer to all kinds of files that have
        nothing to do with your plug-in.

        The file name will be a Python file being executed.  There are two
        broad categories of behavior for a plug-in, depending on the kind of
        files your plug-in supports:

        * Static file names: each of your original source files has been
          converted into a distinct Python file.  Your plug-in is invoked with
          the Python file name, and it maps it back to its original source
          file.

        * Dynamic file names: all of your source files are executed by the same
          Python file.  In this case, your plug-in implements
          :meth:`FileTracer.dynamic_source_filename` to provide the actual
          source file for each execution frame.

        `filename` is a string, the path to the file being considered.  This is
        the absolute real path to the file.  If you are comparing to other
        paths, be sure to take this into account.

        Returns a :class:`FileTracer` object to use to trace `filename`, or
        None if this plug-in cannot trace this file.

        """
        return None

    def file_reporter(self, filename: str) -> FileReporter:      # pylint: disable=unused-argument
        """Get the :class:`FileReporter` class to use for a file.

        Plug-in type: file tracer.

        This will only be invoked if `filename` returns non-None from
        :meth:`file_tracer`.  It's an error to return None from this method.

        Returns a :class:`FileReporter` object to use to report on `filename`,
        or the string `"python"` to have coverage.py treat the file as Python.

        """
        _needs_to_implement(self, "file_reporter")

    def dynamic_context(self, frame) -> None:       # pylint: disable=unused-argument
        """Get the dynamically computed context label for `frame`.

        Plug-in type: dynamic context.

        This method is invoked for each frame when outside of a dynamic
        context, to see if a new dynamic context should be started.  If it
        returns a string, a new context label is set for this and deeper
        frames.  The dynamic context ends when this frame returns.

        Returns a string to start a new dynamic context, or None if no new
        context should be started.

        """
        return None

    def find_executable_files(self, src_dir) -> list[str]:       # pylint: disable=unused-argument
        """Yield all of the executable files in `src_dir`, recursively.

        Plug-in type: file tracer.

        Executability is a plug-in-specific property, but generally means files
        which would have been considered for coverage analysis, had they been
        included automatically.

        Returns or yields a sequence of strings, the paths to files that could
        have been executed, including files that had been executed.

        """
        return []

    def configure(self, config: CoverageConfig) -> None:
        """Modify the configuration of coverage.py.

        Plug-in type: configurer.

        This method is called during coverage.py start-up, to give your plug-in
        a chance to change the configuration.  The `config` parameter is an
        object with :meth:`~coverage.Coverage.get_option` and
        :meth:`~coverage.Coverage.set_option` methods.  Do not call any other
        methods on the `config` object.

        """
        pass

    def sys_info(self) -> list[object]:
        """Get a list of information useful for debugging.

        Plug-in type: any.

        This method will be invoked for ``--debug=sys``.  Your
        plug-in can return any information it wants to be displayed.

        Returns a list of pairs: `[(name, value), ...]`.

        """
        return []


class FileTracer:
    """Support needed for files during the execution phase.

    File tracer plug-ins implement subclasses of FileTracer to return from
    their :meth:`~CoveragePlugin.file_tracer` method.

    You may construct this object from :meth:`CoveragePlugin.file_tracer` any
    way you like.  A natural choice would be to pass the file name given to
    `file_tracer`.

    `FileTracer` objects should only be created in the
    :meth:`CoveragePlugin.file_tracer` method.

    See :ref:`howitworks` for details of the different coverage.py phases.

    """

    def source_filename(self) -> str:
        """The source file name for this file.

        This may be any file name you like.  A key responsibility of a plug-in
        is to own the mapping from Python execution back to whatever source
        file name was originally the source of the code.

        See :meth:`CoveragePlugin.file_tracer` for details about static and
        dynamic file names.

        Returns the file name to credit with this execution.

        """
        _needs_to_implement(self, "source_filename")

    def has_dynamic_source_filename(self) -> bool:
        """Does this FileTracer have dynamic source file names?

        FileTracers can provide dynamically determined file names by
        implementing :meth:`dynamic_source_filename`.  Invoking that function
        is expensive. To determine whether to invoke it, coverage.py uses the
        result of this function to know if it needs to bother invoking
        :meth:`dynamic_source_filename`.

        See :meth:`CoveragePlugin.file_tracer` for details about static and
        dynamic file names.

        Returns True if :meth:`dynamic_source_filename` should be called to get
        dynamic source file names.

        """
        return False

    def dynamic_source_filename(self, filename: str, frame: FrameType) -> str | None:  # pylint: disable=unused-argument
        """Get a dynamically computed source file name.

        Some plug-ins need to compute the source file name dynamically for each
        frame.

        This function will not be invoked if
        :meth:`has_dynamic_source_filename` returns False.

        Returns the source file name for this frame, or None if this frame
        shouldn't be measured.

        """
        return None

    def line_number_range(self, frame: FrameType) -> tuple[int, int]:
        """Get the range of source line numbers for a given a call frame.

        The call frame is examined, and the source line number in the original
        file is returned.  The return value is a pair of numbers, the starting
        line number and the ending line number, both inclusive.  For example,
        returning (5, 7) means that lines 5, 6, and 7 should be considered
        executed.

        This function might decide that the frame doesn't indicate any lines
        from the source file were executed.  Return (-1, -1) in this case to
        tell coverage.py that no lines should be recorded for this frame.

        """
        lineno = frame.f_lineno
        return lineno, lineno


@functools.total_ordering
class FileReporter:
    """Support needed for files during the analysis and reporting phases.

    File tracer plug-ins implement a subclass of `FileReporter`, and return
    instances from their :meth:`CoveragePlugin.file_reporter` method.

    There are many methods here, but only :meth:`lines` is required, to provide
    the set of executable lines in the file.

    See :ref:`howitworks` for details of the different coverage.py phases.

    """

    def __init__(self, filename: str):
        """Simple initialization of a `FileReporter`.

        The `filename` argument is the path to the file being reported.  This
        will be available as the `.filename` attribute on the object.  Other
        method implementations on this base class rely on this attribute.

        """
        self.filename = filename

    def __repr__(self) -> str:
        return "<{0.__class__.__name__} filename={0.filename!r}>".format(self)

    def relative_filename(self) -> str:
        """Get the relative file name for this file.

        This file path will be displayed in reports.  The default
        implementation will supply the actual project-relative file path.  You
        only need to supply this method if you have an unusual syntax for file
        paths.

        """
        return files.relative_filename(self.filename)

    @contract(returns='unicode')
    def source(self) -> str:
        """Get the source for the file.

        Returns a Unicode string.

        The base implementation simply reads the `self.filename` file and
        decodes it as UTF-8.  Override this method if your file isn't readable
        as a text file, or if you need other encoding support.

        """
        with open(self.filename, "rb") as f:
            return f.read().decode("utf-8")

    def lines(self) -> set[int]:
        """Get the executable lines in this file.

        Your plug-in must determine which lines in the file were possibly
        executable.  This method returns a set of those line numbers.

        Returns a set of line numbers.

        """
        _needs_to_implement(self, "lines")

    def excluded_lines(self) -> set[int]:
        """Get the excluded executable lines in this file.

        Your plug-in can use any method it likes to allow the user to exclude
        executable lines from consideration.

        Returns a set of line numbers.

        The base implementation returns the empty set.

        """
        return set()

    def translate_lines(self, lines: Sequence[int]) -> set[int]:
        """Translate recorded lines into reported lines.

        Some file formats will want to report lines slightly differently than
        they are recorded.  For example, Python records the last line of a
        multi-line statement, but reports are nicer if they mention the first
        line.

        Your plug-in can optionally define this method to perform these kinds
        of adjustment.

        `lines` is a sequence of integers, the recorded line numbers.

        Returns a set of integers, the adjusted line numbers.

        The base implementation returns the numbers unchanged.

        """
        return set(lines)

    def arcs(self) -> set[tuple[int, int]]:
        """Get the executable arcs in this file.

        To support branch coverage, your plug-in needs to be able to indicate
        possible execution paths, as a set of line number pairs.  Each pair is
        a `(prev, next)` pair indicating that execution can transition from the
        `prev` line number to the `next` line number.

        Returns a set of pairs of line numbers.  The default implementation
        returns an empty set.

        """
        return set()

    def no_branch_lines(self) -> set[int]:
        """Get the lines excused from branch coverage in this file.

        Your plug-in can use any method it likes to allow the user to exclude
        lines from consideration of branch coverage.

        Returns a set of line numbers.

        The base implementation returns the empty set.

        """
        return set()

    def translate_arcs(self, arcs: set[tuple[int, int]]) -> set[tuple[int, int]]:
        """Translate recorded arcs into reported arcs.

        Similar to :meth:`translate_lines`, but for arcs.  `arcs` is a set of
        line number pairs.

        Returns a set of line number pairs.

        The default implementation returns `arcs` unchanged.

        """
        return arcs

    def exit_counts(self) -> dict[int, int]:
        """Get a count of exits from that each line.

        To determine which lines are branches, coverage.py looks for lines that
        have more than one exit.  This function creates a dict mapping each
        executable line number to a count of how many exits it has.

        To be honest, this feels wrong, and should be refactored.  Let me know
        if you attempt to implement this method in your plug-in...

        """
        return {}

    def missing_arc_description(self, start: int, end: int, executed_arcs: set[int] | None = None) -> str:     # pylint: disable=unused-argument
        """Provide an English sentence describing a missing arc.

        The `start` and `end` arguments are the line numbers of the missing
        arc. Negative numbers indicate entering or exiting code objects.

        The `executed_arcs` argument is a set of line number pairs, the arcs
        that were executed in this file.

        By default, this simply returns the string "Line {start} didn't jump
        to {end}".

        """
        return f"Line {start} didn't jump to line {end}"

    def source_token_lines(self) -> Generator[list[tuple[str, int]], None, None]:
        """Generate a series of tokenized lines, one for each line in `source`.

        These tokens are used for syntax-colored reports.

        Each line is a list of pairs, each pair is a token::

            [('key', 'def'), ('ws', ' '), ('nam', 'hello'), ('op', '('), ... ]

        Each pair has a token class, and the token text.  The token classes
        are:

        * ``'com'``: a comment
        * ``'key'``: a keyword
        * ``'nam'``: a name, or identifier
        * ``'num'``: a number
        * ``'op'``: an operator
        * ``'str'``: a string literal
        * ``'ws'``: some white space
        * ``'txt'``: some other kind of text

        If you concatenate all the token texts, and then join them with
        newlines, you should have your original source back.

        The default implementation simply returns each line tagged as
        ``'txt'``.

        """
        for line in self.source().splitlines():
            yield [('txt', line)]

    def __eq__(self, other: object) -> bool:
        return isinstance(other, FileReporter) and self.filename == other.filename

    def __lt__(self, other: object) -> bool:
        return isinstance(other, FileReporter) and self.filename < other.filename

    __hash__ = None     # This object doesn't need to be hashed.
