#!/usr/bin/env python3

"""An experiment generator for the shared-memory graph partitioner KaMinPar.

This generator is a command-line application which searches for an Experiment.toml
file in the current directory. The configuration file specifies the experiments to
be generated and is thus used to fetch and build KaMinPar and to write script
files, which run the actual experiments.
"""

import hashlib
import inspect
import os
import subprocess
from enum import Enum
from os import listdir, makedirs
from os.path import abspath, dirname, isdir, isfile, join
from pathlib import Path

import tomllib


class Colors:
    """Colors to be used when printing to the console."""

    ARGS = "\033[31m"
    FILE = "\033[34m"
    CMD = "\033[36m"
    EXP = "\033[94m"
    ALGO = "\033[35m"
    FAIL = "\033[91m"
    END = "\033[0m"


def log(msg="", clean=False):
    """Writes a message (optional: with removed leading indentation) to the console."""

    if clean:
        print(inspect.cleandoc(msg))
    else:
        print(msg)


def err(msg):
    """Writes an error message to the console and halts the program."""

    print(f"{Colors.FAIL}{msg.replace(Colors.END, Colors.FAIL)}{Colors.END}")
    exit(1)


def exec(cmd):
    """Executes a command and halts the program if the command fails."""

    print(f"  $ {Colors.CMD}{cmd}{Colors.END}")
    full_cmd = f"{cmd} 2>&1 | sed 's/^/  | /'; exit ${{PIPESTATUS[0]}}"
    result = subprocess.run(["bash", "-c", full_cmd], text=True)

    if result.returncode == 0:
        print("  `-- Exit code: 0\n")
    else:
        err("  `-- Exit code: " + str(result.returncode) + "\n")


def fetch_check_value(data, key, type):
    """Validates whether a dict contains a key and the type of the value associated with the key."""

    if key not in data or not isinstance(data[key], type):
        err(f"Unexpected value type for key {key}!")

    value = data[key]
    del data[key]
    return value


def fetch_check_values(data, key, type):
    """Validates whether a dict contains a key and the types of the list of values associated with the key."""

    if key not in data or not all(isinstance(value, type) for value in data[key]):
        err(f"Unexpected value type for key {key}!")

    value = data[key]
    del data[key]
    return value


def fetch_or_default(data, key, default, type):
    """Fetches a value from a dict or returns a default value otherwise."""

    if key not in data:
        return default

    if not isinstance(data[key], type):
        err(f"Unexpected value type for key {key}!")

    value = data[key]
    del data[key]
    return value


def hash(*args):
    """Creates a MD5-hash of a single or multiple strings."""

    m = hashlib.md5()
    for arg in args:
        if isinstance(arg, list):
            for aarg in arg:
                m.update(hashlib.md5(aarg.encode("utf-8")).digest())
        else:
            m.update(hashlib.md5(arg.encode("utf-8")).digest())
    return m.hexdigest()


def make_executable(path):
    """Makes a file executable."""

    mode = os.stat(path).st_mode
    mode |= (mode & 0o444) >> 2
    os.chmod(path, mode)


class System(str, Enum):
    """System to run the KaMinPar experiment on."""

    GENERIC = "generic"
    BACKGROUND = "background"
    i10_EXCLUSIVE = "i10-exclusive"
    i10_NONEXCLUSIVE = "i10-nonexclusive"

    def generate_wrapper(system, cmd):
        """Wraps a command that is used to invoke a KaMinPar experiment."""

        match system:
            case System.GENERIC:
                return f"bash {cmd}"
            case System.BACKGROUND:
                return f"nohup bash -- {cmd} &\ndisown"
            case System.i10_EXCLUSIVE:
                return f"nohup exclusive bash -- {cmd} &\ndisown"
            case System.i10_NONEXCLUSIVE:
                return f"nohup nonexclusive bash -- {cmd} &\ndisown"
            case _:
                err(f"Unexpected system {system}.")


class CallWrapper(str, Enum):
    """Wrapper to use when invoking KaMinPar."""

    NONE = "none"
    TASKSET = "taskset"
    MPI = "mpi"

    def generate_wrapper(call_wrapper, num_processes, num_threads, cmd):
        """Wraps a command that is used to invoke a KaMinPar algorithm."""

        match call_wrapper:
            case CallWrapper.NONE:
                return cmd
            case CallWrapper.TASKSET:
                return f"taskset -c 0-{num_threads - 1} {cmd}"
            case CallWrapper.MPI:
                return f"mpirun -n {num_processes} --bind-to core --map-by socket:PE={num_threads} {cmd}"
            case _:
                err(f"Unexpected call wrapper {call_wrapper}.")


class Experiment:
    """KaMinPar experiment that consists of several algorithms."""

    def __init__(self, name, config):
        self.name = name
        self.config = config

        self.timeout = fetch_or_default(config, "timeout", 0, int)
        self.processes = fetch_check_values(config, "processes", int)
        self.threads = fetch_check_values(config, "threads", int)
        self.seeds = fetch_check_values(config, "seeds", int)
        self.ks = fetch_check_values(config, "ks", int)
        self.epsilons = fetch_check_values(config, "epsilons", float)

        graphs_path = fetch_check_value(config, "graphs", str)
        if not isdir(graphs_path):
            err(
                f"Directory {Colors.FILE}{graphs_path}{Colors.END} that stores the graphs for experiment {Colors.EXP}{name}{Colors.END} does not exist!"
            )

        self.graphs = [
            abspath(join(graphs_path, file))
            for file in listdir(graphs_path)
            if isfile(join(graphs_path, file))
        ]
        if not self.graphs:
            err(f"Directory {Colors.FILE}{graphs_path}{Colors.END} stores no graphs!")
        else:
            self.graphs.sort()

    def generate(self):
        """Generates a script file that when invoked runs this experiment."""

        starter_name = f"./scripts/{self.name}/starter.sh"
        makedirs(dirname(starter_name), exist_ok=True)

        with open(starter_name, "w") as starter:
            print("#!/usr/bin/env bash", file=starter)
            for algo_name, algo_config in self.config.items():
                if not isinstance(algo_config, dict):
                    err(
                        f"Unexpected configuration for algorithm {Colors.ALGO}{algo_name}{Colors.END} of experiment {Colors.EXP}{self.name}{Colors.END}!"
                    )

                script_path = self.generate_algorithm(algo_name, algo_config)
                print(f"bash {script_path}", file=starter)

        make_executable(starter_name)
        return abspath(starter_name)

    def generate_algorithm(self, algo_name, algo_config):
        """Generates a script file that when invoked runs an algorithm of this experiment."""

        algorithm = Algorithm(algo_name, algo_config)
        if algorithm.hash in generated_sources:
            log(
                f"Algorithm {Colors.ALGO}{algo_name}{Colors.END} has been already build: skipping fetch & build"
            )
        else:
            generated_sources.add(algorithm.hash)
            algorithm.fetch()
            algorithm.build()

        num_graphs = len(self.graphs)
        nl = "\n                "  # Cannot explicitly use backslash in f-string; therefore use this workaround
        log(
            f"""
            Generating calls for algorithm {Colors.ALGO}{algo_name}{Colors.END} using:
            - Binary: {Colors.FILE}{algorithm.binary_path()}{Colors.END}
            - Generated arguments:
                -T {nl + "-H" if algorithm.heap_profiled() else ""}
                -G {Colors.ARGS}[{self.graphs[0] if num_graphs == 1 else " ... ".join(self.graphs[::num_graphs - 1])}]{Colors.END}
                -t {Colors.ARGS}{self.threads}{Colors.END}
                -k {Colors.ARGS}{self.ks}{Colors.END}
                -e {Colors.ARGS}{self.epsilons}{Colors.END}
                -s {Colors.ARGS}{self.seeds}{Colors.END}
            - Specified arguments:\
            """,
            clean=True,
        )
        for arg in algorithm.args:
            log(f"    {Colors.ARGS}{arg}{Colors.END}")
        log()

        script_name = f"./scripts/{self.name}/{algo_name}.sh"
        makedirs(dirname(script_name), exist_ok=True)

        log_dir = f"./logs/{self.name}/{algo_name}"
        makedirs(log_dir, exist_ok=True)

        with open(script_name, "w") as script:
            print("#!/usr/bin/env bash", file=script)
            for graph in self.graphs:
                for num_processes in self.processes:
                    for num_threads in self.threads:
                        for k in self.ks:
                            for epsilon in self.epsilons:
                                for seed in self.seeds:
                                    generated_arguments = f"-T -G {graph} -t {num_threads} -k {k} -e {epsilon} -s {seed}"
                                    if algorithm.heap_profiled():
                                        generated_arguments = (
                                            f"-H {generated_arguments}"
                                        )

                                    specified_arguments = " ".join(algorithm.args)
                                    log_file = abspath(
                                        f"{log_dir}/{Path(graph).stem}___P1x{num_processes}x{num_threads}_seed{seed}_eps{epsilon}_k{k}.log"
                                    )
                                    cmd = f"{algorithm.binary_path()} {generated_arguments} {specified_arguments} >> {log_file} 2>&1"

                                    cmd = CallWrapper.generate_wrapper(
                                        call_wrapper, num_processes, num_threads, cmd
                                    )
                                    if self.timeout > 0:
                                        cmd = f"timeout -v {self.timeout}m {cmd}"
                                    if time_cmd:
                                        cmd = f"{time_cmd} -v {cmd}"

                                    commands.append((graph, cmd))
                                    print(cmd, file=script)

        make_executable(script_name)
        return abspath(script_name)


class Algorithm:
    """KaMinPar algorithm that defines the source files, build process and arguments for running KaMinPar."""

    def __init__(self, name, config):
        self.name = name
        self.config = config

        self.git_url = fetch_check_value(config, "git-url", str)
        self.branch = fetch_or_default(config, "branch", "main", str)
        self.target = fetch_or_default(config, "target", "KaMinPar", str)
        self.compile_flags = fetch_check_values(config, "compile-flags", str)
        self.args = fetch_check_values(config, "args", str)

        self.hash = hash(self.git_url, self.branch, self.compile_flags)
        self.src_dir = abspath(f"./src/{self.hash}")

    def fetch(self):
        """Fetches the source files of this KaMinPar algorithm."""

        # Use fixed length of the hash value as an indicator of a detached head, which can result in false positives.
        detached_head = len(self.branch) == 40

        if detached_head and isdir(self.src_dir):
            log(
                f"Directory {Colors.FILE}{self.src_dir}{Colors.END} for algorithm {Colors.ALGO}{self.name}{Colors.END} is in detached head: skipping fetch"
            )
            return
        elif not isdir(self.src_dir):
            log(
                f"Directory {Colors.FILE}{self.src_dir}{Colors.END} for algorithm {Colors.ALGO}{self.name}{Colors.END} does not exist: initialize from a remote Git repository"
            )
            exec(f"git clone --recurse-submodules {self.git_url} {self.src_dir}")
        else:
            log(
                f"Directory {Colors.FILE}{self.src_dir}{Colors.END} for algorithm {Colors.ALGO}{self.name}{Colors.END} does already exist: update from a remote Git repository"
            )

        exec(f"git -C {self.src_dir} pull --all")
        exec(f"git -C {self.src_dir} submodule update --recursive")
        exec(
            f"git -C {self.src_dir} -c advice.detachedHead=false checkout {self.branch}"
        )

    def build(self):
        """Builds this KaMinPar algorithm that was previously fetched."""

        log(
            f"Build algorithm {Colors.ALGO}{self.name}{Colors.END} in directory {Colors.FILE}{self.src_dir}{Colors.END}"
        )
        exec(
            f"cmake -S {self.src_dir} -B {self.src_dir}/build -DCMAKE_BUILD_TYPE=Release -DKAMINPAR_BUILD_DISTRIBUTED=On -DKAMINPAR_BUILD_TESTS=Off -DKAMINPAR_BUILD_BENCHMARKS=On {' '.join(self.compile_flags)}"
        )
        exec(f"cmake --build {self.src_dir}/build --target {self.target} --parallel")

    def binary_path(self):
        """Returns the binary path of the result of previously building this KaMinPar algorithm."""

        if self.target == "KaMinPar":
            return abspath(f"{self.src_dir}/build/apps/KaMinPar")

        if self.target == "dKaMinPar":
            return abspath(f"{self.src_dir}/build/apps/dKaMinPar")

        return abspath(f"{self.src_dir}/build/benchmarks/{self.target}")

    def heap_profiled(self):
        """Returns whether the heap profiler is enabled for this KaMinPar algorithm."""

        return "-DKAMINPAR_ENABLE_HEAP_PROFILING=On" in self.compile_flags


if not isfile("Experiment.toml"):
    err("The current directory does not contain an experiment configuration file.")

with open("Experiment.toml", "rb") as file:
    data = tomllib.load(file)

    system = fetch_or_default(data, "system", System.GENERIC, str)
    call_wrapper = fetch_or_default(data, "call-wrapper", CallWrapper.NONE, str)
    time_cmd = fetch_or_default(data, "time-cmd", "", str)

    # Stores the hash values of the source files that are generated to only
    # fetch and build source files once.
    generated_sources = set()

    # Stores the commands that are generated together with the input graph to
    # create a script with all input graphs in sorted order.
    commands = list()

    # Generate all experiments and add their starting script to the submission script.
    submit_name = "./submit.sh"
    with open(submit_name, "w") as submit:
        print("#!/usr/bin/env bash", file=submit)

        for name, config in data.items():
            if not isinstance(config, dict):
                err(
                    f"Unexpected configuration for experiment {Colors.EXP}{name}{Colors.END}!"
                )

            experiment = Experiment(name, config)
            script_name = experiment.generate()

            print(System.generate_wrapper(system, script_name), file=submit)
    make_executable(submit_name)

    # Generate a submission script that runs all commands by input graphs in
    # alphabetical order.
    commands.sort(key=lambda x: x[0])
    submit_all_name = "./submit-ordered.sh"
    starter_all_name = "./scripts/ordered-starter.sh"
    with open(submit_all_name, "w") as submit_all:
        print("#!/usr/bin/env bash", file=submit_all)
        print(System.generate_wrapper(system, starter_all_name), file=submit_all)

        with open(starter_all_name, "w") as starter_all:
            print("#!/usr/bin/env bash", file=starter_all)

            for _, cmd in commands:
                print(cmd, file=starter_all)
    make_executable(submit_all_name)
