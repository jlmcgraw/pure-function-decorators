# Frequently asked questions

## Can the decorators be enabled globally, similar to Perl's `strict` pragma?

Not currently. Python does not expose a way to automatically wrap every function or method that gets imported or defined after a module loads. Each decorator in this project returns a new callable, so you must opt in on a per-function basis (or build your own helper that walks a module or class and decorates the objects you choose). The library therefore cannot enforce purity checks globally without explicit wrapping.

## Could the descriptor protocol automatically apply the decorators to methods?

Not in a general way. Python already turns functions defined on a class into descriptors, and replacing them with a custom descriptor still requires opting in for every attribute that you assign. Descriptors also do not help with module-level functions or with classes defined in third-party code. You can create a metaclass or `__setattr__` hook that decorates attributes as they are stored on a specific class hierarchy, but that only moves the opt-in boundary to "use this special base class" rather than providing a library-wide switch that patches every callable in the interpreter.
