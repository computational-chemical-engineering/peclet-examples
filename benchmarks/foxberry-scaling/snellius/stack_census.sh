#!/bin/bash
# Stack census of a running job, PARALLEL gdb attach (16 at a time, 6 s each) so 192 ranks fit in
# a few minutes. Tallies the innermost solver frame and the MPI call per rank on the chosen node
# index(es). Usage: stack_census.sh <jobid> [i...]
J=$1; shift; IDX="${@:-1}"
for i in $IDX; do
  N=$(scontrol show hostnames "$(squeue -j $J -h -o %N)" | sed -n "${i}p")
  echo "##### job $J node $N"
  srun --jobid=$J --overlap --nodes=1 --ntasks=1 --cpus-per-task=16 -w $N --time=00:12:00 bash -c '
    T=$(mktemp -d)
    pgrep -u $USER -x python | xargs -P 16 -I{} sh -c "timeout 6 gdb -batch -p {} -ex \"bt 16\" > $T/{}.bt 2>/dev/null"
    echo "--- ranks sampled: $(ls $T | wc -l)"
    echo "--- innermost non-MPI frame per rank:"
    for f in $T/*.bt; do grep -E "^#[0-9]+ " $f | grep -vE "ucs_|ucp_|uct_|opal_|ompi_|libc\.so|clone|start_thread|mca_pml|PMPI_|MPI_|\?\?" | head -1 | sed -E "s/^#[0-9]+ +(0x[0-9a-f]+ in )?//; s/ \(.*//; s/ from .*//; s/ at .*//"; done | sort | uniq -c | sort -rn | head -14
    echo "--- top MPI call per rank:"
    for f in $T/*.bt; do grep -oE "PMPI_[A-Za-z_]+" $f | head -1; done | sort | uniq -c | sort -rn
    echo "--- one full stack (first rank):"
    head -16 $(ls $T/*.bt | head -1) | grep -E "^#" | cut -c1-150
    rm -rf $T
  ' 2>&1 | grep -v "^srun"
done
