#!/bin/bash
# This plugin checks IB.devices.
readonly EXPECTED_IB_Gbps=400
readonly EXPECTED_IB_DEVS="mlx5_0:1 mlx5_1:1 mlx5_2:1 mlx5_3:1 mlx5_4:1 mlx5_5:1 mlx5_6:1 mlx5_7:1"

HW_IB_STATE=( )
HW_IB_PHYS_STATE=()
HW_IB_RATE=( )
HW_IB_DEV=()

function gather_ib_data() {
    local IFS LINE CORES SIBLINGS MHZ PROCESSOR PHYS_ID PORT INDEX DEV
    local -a FIELD PHYS_IDS IB_PORTS

# Gather IB info
    set +f
    IFS=''
    IB_PORTS=( /sys/class/infiniband/*/ports/* )
    IFS=$' \t\n'
    set -f
    for PORT in "${IB_PORTS[@]}" ; do
        test -e "$PORT" || break
        INDEX=${#HW_IB_STATE[*]}
        IFS=' :'
        read LINE < $PORT/state
        FIELD=( $LINE )
        HW_IB_STATE[$INDEX]=${FIELD[1]}
        read LINE < $PORT/phys_state
        FIELD=( $LINE )
        HW_IB_PHYS_STATE[$INDEX]=${FIELD[1]}
        read LINE < $PORT/rate
        FIELD=( $LINE )
        HW_IB_RATE[$INDEX]=${FIELD[0]}
        IFS=' /'
        arr=( $PORT )
        HW_IB_DEV[$INDEX]="${arr[4]}:${arr[6]}"
        IFS=$' \t\n'
#        echo "Found ${HW_IB_STATE[$INDEX]} (${HW_IB_PHYS_STATE[$INDEX]}) IB Port ${HW_IB_DEV[$INDEX]} (${HW_IB_RATE[$INDEX]} Gb/sec)"
    done
    export HW_IB_STATE HW_IB_PHYS_STATE HW_IB_RATE

# Check if user-leved mad driver loaded and IB diag tools will succeed to run
    if [[ -f /sys/class/infiniband_mad/abi_version ]]; then
       read HW_IB_UMAD_ABI_VER < /sys/class/infiniband_mad/abi_version
    else
       HW_IB_UMAD_ABI_VER=0
    fi
    export HW_IB_UMAD_ABI_VER
}
# Check if IB state, phys_state, and rate ($1) all match.
function check_ib() {
    local STATE="ACTIVE"
    local PHYS_STATE="LinkUp"
    local RATE="$1"
    local DEV="$2"
    local i

    if [[ ${#HW_IB_STATE[*]} -eq 0 ]]; then
       gather_ib_data
    fi

    if [[ $HW_IB_UMAD_ABI_VER -eq 0 ]]; then
       echo "Version mismatch between kernel OFED drivers and userspace OFED libraries."
       exit 1
    fi

    for ((i=0; i < ${#HW_IB_STATE[*]}; i++)); do
        if [[ "${HW_IB_STATE[$i]}" == "$STATE" && "${HW_IB_PHYS_STATE[$i]}" == "$PHYS_STATE" ]]; then
           if [[ (-z "$DEV" || "${HW_IB_DEV[$i]}" == "$DEV") && (-z "$RATE" || "${HW_IB_RATE[$i]}" == "$RATE") ]]; then
              return 0
           fi
        fi
    done

    if [[ -n "$DEV" ]]; then
       DEV=" $DEV"
    fi
    if [[ -n "$RATE" ]]; then
       RATE=" $RATE Gb/sec"
    fi

    echo "No IB port$DEV is $STATE ($PHYS_STATE$RATE)."
    exit 1
}

for ib_dev in $EXPECTED_IB_DEVS
do
    check_ib $EXPECTED_IB_Gbps $ib_dev
done

echo "IB devices are ok"
exit 0 