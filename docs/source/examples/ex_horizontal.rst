..
  NOTE: This RST file was generated by `make examples`.
  Do not edit it directly.
  See docs/source/examples/example_doc_generator.py

Horizontal Example
===============================================================================

An example of the ``horizontal`` layout helper.

This example uses the ``horizontal`` layout helper to arrange a series of
``PushButton`` widgets in a horizontal layout. No constraints are placed
on the vertical position of the ``PushButton`` widgets so their vertical
location in this example is non-deterministic.

.. TIP:: To see this example in action, download it from
 :download:`horizontal <../../../examples/layout/basic/horizontal.enaml>`
 and run::

   $ enaml-run horizontal.enaml


Screenshot
-------------------------------------------------------------------------------

.. image:: images/ex_horizontal.png

Example Enaml Code
-------------------------------------------------------------------------------
.. literalinclude:: ../../../examples/layout/basic/horizontal.enaml
    :language: enaml
