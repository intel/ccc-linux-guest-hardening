# Quick summary of findings
#
# Scan all logs for some crash/issue identifier, e.g. "RIP:" or KASAN: string.
# Then reverse-sort to get a mapping of unique identifiers to logs per harness
# Also report any crash logs that could not be associated to a crash identifier

dir=$1

cd $dir

LOGS_CRASH="logs_crash.lst"
LOGS_KASAN="logs_kasan.lst"
LOGS_TIMEO="logs_timeo.lst"

find */logs -name crash_\* > $LOGS_CRASH
find */logs -name kasan_\* > $LOGS_KASAN
find */logs -name timeo_\* > $LOGS_TIMEO
	
num_crash=$(cat $LOGS_CRASH|wc -l)
num_kasan=$(cat $LOGS_KASAN|wc -l)
num_timeo=$(cat $LOGS_TIMEO|wc -l)

SCAN_LOGS="$LOGS_CRASH $LOGS_KASAN"

declare -A tag2log
declare -A tag2msg

register_issue() {
	msg=$1
	log=$2

	tag=$(echo "$msg"|cksum -|cut -b -6)
	if test -z "${tag2msg[$tag]}"; then
		tag2msg[$tag]="$msg"
		tag2log[$tag]="$log"
	else
		tag2log[$tag]="${tag2log[$tag]},$log"
	fi
	#echo -e "$tag;$msg;$log"
}

for log in $(cat $SCAN_LOGS); do
	## catch-all for common panic(??) handler, where RIP is shown shortly after error type + "SMP KASAN NOPTI" string
	msg=$(grep -v '^ \? \|^Call Trace:' $log|grep -A 2 'KASAN NOPTI$'|grep '^RIP:\|KASAN NOPTI$'|sed s/'SMP KASAN NOPTI'//|tr -d '\n')
	if test -n "$msg"; then
		register_issue "$msg" "$log"
		continue
	fi

	## fallback: look 2-3 lines backward from RIP to find possible error cdoe
	# this is less nice because RIP: line can occur multiple times
	msg=$(grep -v '^ \? \|^Call Trace:' $log|grep -B 3 ^RIP:|grep -v ^CPU:|sed s/\(.*//|tr -d '\n')
	if test -n "$msg"; then
		register_issue "$msg" "$log"
		continue
	fi

	register_issue "unclassified" "$log"
done

rm $LOGS_CRASH
rm $LOGS_KASAN
rm $LOGS_TIMEO


for tag in ${!tag2msg[*]}; do
	echo -e "$tag;${tag2msg[$tag]};${tag2log[$tag]};"
done > summary.csv

(
	echo "Scanned $num_crash crash logs, $num_kasan sanitizer logs, $num_timeo timeouts"
	echo "Identified ${#tag2msg[*]} issues: ${!tag2msg[@]}"
	for tag in ${!tag2msg[*]}; do
		logs="$(echo "${tag2log[$tag]}"|sed 's/,/,\n\t/g')"
		echo -e "[$tag] ${tag2msg[$tag]}\n\t$logs\n"
	done
) > summary.txt

(
	echo '<pre>'
	echo "Scanned logs: $num_crash crashes, $num_kasan sanitizer, $num_timeo timeouts"
	echo "Identified ${#tag2msg[*]} issues: ${!tag2msg[@]}"
	for tag in ${!tag2msg[*]}; do
		echo "<p>"
		echo -e "[$tag] ${tag2msg[$tag]}"
		logs="$(echo "${tag2log[$tag]}"|sed 's/,/\n/g')"
		for log in $logs; do
			echo -e "\t<a href="$log">$log</a>"
		done
	done
	echo '</pre>'
) > summary.html


