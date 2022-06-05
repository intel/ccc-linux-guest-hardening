# Quick summary of findings
#
# Scan all logs for some crash/issue identifier, e.g. "RIP:" or KASAN: string.
# Then reverse-sort to get a mapping of unique identifiers to logs per harness
# Also report any crash logs that could not be associated to a crash identifier

dir=$1
cd $dir || exit

LOGS_CRASH="logs_crash.lst"
LOGS_KASAN="logs_kasan.lst"
LOGS_TIMEO="logs_timeo.lst"

# which logs to scan? timeout logs can be crappy
SCAN_LOGS="$LOGS_KASAN $LOGS_CRASH"
SCAN_LOGS="$LOGS_KASAN $LOGS_CRASH $LOGS_TIMEO"

# order of bug classes to print (will only print these!)
CLASSES_ORDER="KASAN CRASH WARNS HANGS"

# identify panic handler reason based on build config :-/
PANIC_STRING='SMP KASAN NOPTI$'

find */logs -name crash_\* > $LOGS_CRASH
find */logs -name kasan_\* > $LOGS_KASAN
find */logs -name timeo_\* > $LOGS_TIMEO

declare -A tag2msg
declare -A tag2log
declare -A class2tag

register_issue() {
	msg=$1
	log=$2
	class=$3
	TAGLEN=5

	if test -n "$msg"; then
		msg=$(echo "$msg"|grep -v '^ \? \|^Call Trace:\|^CPU:\|^Code:\|^CR2:\|^CS:\|^FS:\|^R13:\|^R10:\|^RBP:\|^RDX:\|^RSP:')
		# shorten #GP, remove line offsets, and stuck-at detail
		msg=$(echo "$msg"|sed -e 's/general protection fault/#GF/' -e 's/+0x[0-9,a-f,x,/]*//g' -e 's/stuck for [0-9]*s.*/stuck for N secs/' -e 's/RIP: 0010:/RIP: /')
		msg=$(echo "$msg"|tr '\n' ' '|sed 's/general protection fault/#GP/')
		tag=$(echo "$msg,$class"|cksum -|cut -b -$TAGLEN)

		if ! echo "$CLASSES_ORDER"|grep -q $class; then
			echo "Warning: error class $class will not be printed."
		fi

		if test -z "${tag2msg[$tag]}"; then
			tag2msg[$tag]="$msg"
			tag2log[$tag]="$log"

			if test -z "${class2tag[$class]}"; then
				class2tag[$class]="$tag"
			else
				class2tag[$class]="${class2tag[$class]} $tag"
			fi
		else
			tag2log[$tag]="${tag2log[$tag]},$log"
		fi


		#echo -e "$tag;$msg;$log"
		return 0
	else
		return 1
	fi
}

for log in $(cat $SCAN_LOGS); do
	# explicit (outline?) KASAN results reported by bug() handler
	msg=$(grep -A 1 '^BUG: KASAN:' $log|sed 's/^BUG: //')
	register_issue "$msg" "$log" "KASAN" && continue

	## catch KASAN reported as part of general #GP crash handler (CONFIG_KASAN_INLINE)
	msg=$(grep -A 3 '^KASAN:' $log|grep '^RIP:\|^KASAN:')
	register_issue "$msg" "$log" "KASAN" && continue

	## catch common panic() handler, where RIP is shown shortly after error type + build flags "SMP KASAN NOPTI" string
	# some of these may contain an additional KASAN: line but we probably cought those in previous rule..
	msg=$(grep -v '^CPU:\|^Modules linked in:' $log|grep -m 2 -A 3 'KASAN NOPTI$'|grep '^RIP:\|^KASAN:\|KASAN NOPTI$'|sed s/'SMP KASAN NOPTI'//)
	register_issue "$msg" "$log" "CRASH" && continue

	## catch unchecked MSR access
	msg=$(grep -m 1 '^unchecked MSR access error:' $log)
	register_issue "$msg" "$log" "WARNS" && continue

	## catch WARNING: and BUG:, - look at first two RIPs in case there is some useful output in between
	msg=$(grep -v '^CPU:\|^Modules linked in:' $log|grep -m 2 '^WARNING:\|^BUG:'|sed s/'SMP KASAN NOPTI'//)
	msg=$(echo "$msg"|grep -v '^ ? \|^Call Trace:\|^Code:\|^CR2:\|^CS:\|^FS:\|^R13:\|^R10:\|^RBP:\|^RDX:\|^RSP:')
	register_issue "$msg" "$log" "WARNS" && continue

	## fallback: look 2-3 lines backward from RIP extract any other issues
	# look at first 2 RIP matches and remove CPU/stack info
	#msg=$(grep -v '^ ? \|^Call Trace:' $log|grep -m 1 -B 2 ^RIP:|sed s/\(.*//)
	msg=$(grep -v '^CPU:\|^Modules linked in:' $log| grep -m 2 -B 1 ^RIP:|sed s/\(.*//)
	msg=$(echo "$msg"|grep -v '^ ? \|^Call Trace:\|^Code:\|^CR2:\|^CS:\|^FS:\|^R13:\|^R10:\|^RBP:\|^RDX:\|^RSP:')
	register_issue "$msg" "$log" "WARNS" && continue

	if grep -q $log $LOGS_TIMEO; then
		register_issue "Unclassified HANGS" "$log" "HANGS"
	else
		register_issue "Unclassified CRASH" "$log" "WARNS"
	fi
done

SCAN_LOGS_NUM=$(cat $SCAN_LOGS|wc -l)
rm $LOGS_CRASH
rm $LOGS_KASAN
rm $LOGS_TIMEO


for tag in ${!tag2msg[*]}; do
	echo -e "$tag;${tag2msg[$tag]};${tag2log[$tag]};"
done > summary.csv

(
	echo "Scanned logs: $SCAN_LOGS ($SCAN_LOGS_NUM logs total)"
	echo "Identified ${#tag2msg[*]} issues:"
	for class in $CLASSES_ORDER; do
		[ -n "${class2tag[$class]}" ] && echo -e "\t$class: ${class2tag[$class]}"
	done
	echo
	for class in $CLASSES_ORDER; do
		for tag in ${class2tag[$class]}; do
			logs="$(echo "${tag2log[$tag]}"|sed 's/,/,\n\t/g')"
			echo -e "[$tag] ${tag2msg[$tag]}\n\t$logs\n"
		done
	done
) > summary.txt

(
	echo '<pre>'
	echo "Scanned logs: $SCAN_LOGS ($SCAN_LOGS_NUM logs total)"
	echo "Identified ${#tag2msg[*]} issues:"
	for class in $CLASSES_ORDER; do
		[ -z "${class2tag[$class]}" ] && continue
		num_issues=$(echo ${class2tag[$class]}|wc -w)
		printf "\t%8s: ${class2tag[$class]}\n" "$num_issues $class"
	done
	echo "<p>"
	for class in $CLASSES_ORDER; do
		[ -z "${class2tag[$class]}" ] && continue
		case $class in
			"KASAN"|"CRASH")
				echo "<details open>"
				;;
			*)
				echo "<details>"
				;;
		esac
		num_issues=$(echo ${class2tag[$class]}|wc -w)
		echo "<summary><b>Category $class ($num_issues items)</b></summary>"
		for tag in ${class2tag[$class]}; do
			echo -e "  <b>[$tag] ${tag2msg[$tag]}</b>"
			logs="$(echo "${tag2log[$tag]}"|sed 's/,/\n/g')"
			for log in $logs; do
				# check for some extra warnings/errors to spot different logs
				note=$(tac $log|grep -i -m 1 "error\|fatal\|warn\|fail")
				[ -n "$note" ] && note=$(echo "<i>last error:</i> $note"|sed 's/+0x[0-9,a-f,x,/]*//g')
				printf "\t<a href=\"$log\"%-62s %s\n" ">$log</a>" "$note"
			done
			echo "<p />"
		done
		echo "</details>"
	done
	echo '</pre>'
) > summary.html


