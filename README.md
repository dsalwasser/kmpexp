# kmpexp

kmpexp is an experiment generator for the shared-memory and distributed-memory
graph partitioner [KaMinPar](https://github.com/KaHIP/KaMinPar).

## How to build

Simply clone this repository and make sure that `kmpexp.py` is available in
the command-line. Furthermore, if you use Python before version 3.11 make sure
that `kmpexp.py` can access the tomllib directory contained in this repository.

### Nix

If you use the Nix package manager, you can start kmpexp as follows:
```
nix run github:dsalwasser/kmpexp
```

## How to use

Create an `Experiment.toml` file in the directory you want to set up the
experiment. This file contains the configuration of the experiment. Then, run
`kmpexp.py` inside that directory to fetch and build KaMinPar according to the
configuration and to write the scripts that run the experiment. Finally,
execute `submit.sh` to start the experiment. Alternatively, you can execute
`submit-ordered.sh` to start the experiment and run all commands ordered by
input graphs in alphabetical order.
