# Frequently asked questions

## Can the decorators be enabled globally, similar to Perl's `strict` pragma?

Not currently. Python does not expose a way to automatically wrap every function or method that gets imported or defined after a module loads. Each decorator in this project returns a new callable, so you must opt in on a per-function basis (or build your own helper that walks a module or class and decorates the objects you choose). The library therefore cannot enforce purity checks globally without explicit wrapping.
