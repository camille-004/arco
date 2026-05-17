# Arco

A desktop bowed-string instrument. Two touch strips — left hand selects pitch, right hand bows. Physically modeled waveguide synthesis on a Teensy 4.0.

## Prototype

Requires Python 3.14+, [uv](https://github.com/astral-sh/uv), and [just](https://github.com/casey/just).

```bash
just run
```

Controls: `ASDFG` = pitch, mouse = bow, `P` = preset, `Q` = quit.

## Development

```bash
just lint        # ruff linter
just fmt         # ruff formatter
just typecheck   # ty type checker
just check       # all three
just hooks       # install pre-commit hooks
```

## Hardware

See `docs/Arco Instrument Design Specification.pdf` for full design specification and parts list (~$73).
