#!/bin/bash
# This plugin checks GPU XID errors
readonly OK=0
readonly NONOK=1
readonly UNKNOWN=2

GPU_REMAPPED_ROWS_QUERY="remapped_rows.pending,remapped_rows.failure,remapped_rows.uncorrectable"
GPU_QUERY="ecc.errors.uncorrected.volatile.sram,ecc.errors.uncorrected.aggregate.sram,ecc.errors.uncorrected.volatile.dram,ecc.errors.uncorrected.aggregate.dram,ecc.errors.corrected.volatile.sram,ecc.errors.corrected.aggregate.sram,ecc.errors.corrected.volatile.dram,ecc.errors.corrected.aggregate.dram"

function collect_ecc_data() {
   ECC_TYPE=$1

   if [[ $ECC_TYPE == "SDBE" ]]; then
# implement collect data
      page_retirement_query_out=$(nvidia-smi -q -d PAGE_RETIREMENT)
      page_retirement_query_out_rc=$?

      if [[ $page_retirement_query_out_rc != 0 ]]; then
         echo "nvidia-smi (get page retirement table) returned error code $page_retirement_query_out_rc. FaultCode: NHCNA"
         exit $UNKNOWN
      fi
      IFS=$'\n'
      TAB=$'\t'
      echo ""
   else
      gpu_query_out=$(nvidia-smi --query-gpu=$GPU_QUERY --format=csv,noheader)
      gpu_query_out_rc=$?
      if [[ $gpu_query_out_rc != 0 ]]
      then
      echo "nvidia-smi (get gpu uncorrected counts) returned error code $gpu_query_out_rc. FaultCode: NHCNA"
      exit $UNKNOWN
      fi
      gpu_remapped_rows_out=$(nvidia-smi --query-remapped-rows=$GPU_REMAPPED_ROWS_QUERY --format=csv,noheader)
      gpu_remapped_rows_out_rc=$?
      if [[ $gpu_remapped_rows_out_rc != 0 ]]
      then
      echo "nvidia-smi (get gpu remapped rows) returned error code $gpu_freq_out_rc. FaultCode: NHCNA"
      exit $UNKNOWN
      fi
      IFS=$'\n'
      gpu_query_out_lines=( $gpu_query_out )
      gpu_remapped_rows_query_out_lines=( $gpu_remapped_rows_out )
      IFS=$' \t\n'
   fi
}

# ECC checks for A100/H100
function check_ecc() {

   collect_ecc_data "ECC"

   ecc_error_threshold=$1
   ecc_sram_threshold=$2

   if [[ ${#gpu_query_out_lines[*]} != ${#gpu_remapped_rows_query_out_lines[*]} ]]; then
      echo "nvidia-smi (Number GPU's not correct), (${#gpu_query_out_lines[*]},${#gpu_remapped_rows_query_out_lines[*]}). FaultCode: NHC2007"
      exit $NONOK
   fi
   for ((i=0; i<${#gpu_remapped_rows_query_out_lines[*]}; i++))
   do
      IFS=$', '
      gpu_remapped_rows_query_out_line=( ${gpu_remapped_rows_query_out_lines[$i]} )
      gpu_query_out_line=( ${gpu_query_out_lines[$i]} )
      IFS=$' \t\n'
      if [[ ${gpu_remapped_rows_query_out_line[0]} -gt 0 ]]
      then
         echo "GPU id $i: Row remap pending. FaultCode: NHC2007"
         exit $NONOK
      fi
      if [[ ${gpu_remapped_rows_query_out_line[1]} -gt 0 ]]
      then
        echo "GPU id $i: Row remap error. FaultCode: NHC2007"
        exit $NONOK
      fi
      echo "GPU id $i: row remap uncorrectable error count, (${gpu_remapped_rows_query_out_line[3]})"
      if [[ ${gpu_remapped_rows_query_out_line[3]} -gt 512 ]]
      then
         echo "GPU id $i: Row remap uncorrectable error count is too high. FaultCode: NHC2007"
         exit $NONOK
      fi
      if [[ ${gpu_query_out_line[4]} -gt $ecc_sram_threshold || ${gpu_query_out_line[5]} -gt $ecc_sram_threshold ]]; then
         echo "GPU id $i: High SRAM correctable ECC error count detected, (${gpu_query_out_line[4]},${gpu_query_out_line[5]}). FaultCode: NHC2019"
         exit $NONOK
      elif [[ ${gpu_query_out_line[0]} -gt 0 || ${gpu_query_out_line[1]} -gt 0 ]]; then
         echo "GPU id $i: SRAM Uncorrectable ECC error count detected, (${gpu_query_out_line[0]},${gpu_query_out_line[1]}). FaultCode: NHC2019"
         exit $NONOK
      else
         echo "GPU id $i: Normal SRAM Uncorrectable/correctable ECC error count, (${gpu_query_out_line[0]},${gpu_query_out_line[1]},${gpu_query_out_line[4]},${gpu_query_out_line[5]})"
      fi
      if [[ -n $ecc_error_threshold ]]; then
         if [[ ${gpu_query_out_line[2]} -gt $ecc_error_threshold || ${gpu_query_out_line[3]} -gt $ecc_error_threshold || ${gpu_query_out_line[6]} -gt $ecc_error_threshold || ${gpu_query_out_line[7]} -gt $ecc_error_threshold ]]; then
            echo "GPU id $i: High DRAM Uncorrectable/correctable ECC error count detected, (${gpu_query_out_line[2]},${gpu_query_out_line[3]},${gpu_query_out_line[6]},${gpu_query_out_line[7]}). FaultCode: NHC2019"
            exit $NONOK
         else
            echo "GPU id $i: Normal DRAM Uncorrectable/correctable ECC error count, (${gpu_query_out_line[2]},${gpu_query_out_line[3]},${gpu_query_out_line[6]},${gpu_query_out_line[7]})"
         fi
      fi
   done
   exit 0
}

function check_SDBE_ecc() {
   collect_ecc_data "SDBE"
   flag="false"
   error_msg=''
   re='^[0-9]+$'

# Implement check of collected value against limits
   gpu_sections=($(echo "$page_retirement_query_out" | awk '/GPU / {print $0}'))
   sbe_sections=($(echo "$page_retirement_query_out" | awk '/Single Bit ECC / {print $NF}'))
   dbe_sections=($(echo "$page_retirement_query_out" | awk '/Double Bit ECC / {print $NF}'))
   ppending_blacklist_sections=($(echo "$page_retirement_query_out" | awk '/Pending Page Blacklist / {print $NF}'))

# implement SBE DBE total check
# Process each GPU section
   for index in "${!gpu_sections[@]}"; do
# Extract SBE and DBE values
      gpu=${gpu_sections[index]}
      sbe=${sbe_sections[index]}
      dbe=${dbe_sections[index]}

      if ! [[ $sbe =~ $re ]] || ! [[ $dbe =~ $re ]]; then
         continue
      fi

# Calculate the sum of SBE and DBE pages
      total=$((sbe + dbe))

# implement page retirement check
# Check if page blacklist is pending
      pending=${ppending_blacklist_sections[index]}

      if [ "$total" -ge 62 ] && [ "$pending" == "Yes" ]; then
         log "$FUNCNAME: Retirement Table Full for, GPU section: GPU=$gpu Total Pages=$total, Pending Blacklist=$pending"
         flag="true"
         error_msg+="$TAB : Retirement Table Full for, GPU: $gpu, Total Pages: $total, Pending Blacklist: $pending$IFS"
      fi
   done

   if [ "$flag" == "true" ]; then
      echo "ERROR: $IFS$error_msg. FaultCode: NHC2018"
      exit $NONOK
   fi

   exit $OK
}

function check_gpu_ecc() {
   if lspci | grep -i 'VGA\|3D controller'| grep -qi 'V100'; then
     check_SDBE_ecc
   else
     ecc_error_threshold=$1
     ecc_sram_threshold=$2
     check_ecc $ecc_error_threshold $ecc_sram_threshold
   fi

   echo "ECC checks passed"
   exit $NONOK
} 