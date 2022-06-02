# Quick summary of findings
#
# Scan all logs for some crash/issue identifier, e.g. "RIP:" or KASAN: string.
# Then reverse-sort to get a mapping of unique identifiers to logs per harness
# Also report any crash logs that could not be associated to a crash identifier

dir=$1

cd $dir

find */logs -name crash_\* > crash.lst
find */logs -name timeo_\* > timeo.lst
find */logs -name kasan_\* > kasan.lst

declare -A tag2log
declare -A tag2msg

register_issue() {
	msg=$1
	log=$2

	tag=$(echo "$msg"|cksum -|cut -b -6)
	if test -z "${tag2msg[$tag]}"; then
		tag2msg[$tag]="$msg"
		tag2log[$tag]="\t$log"
	else
		tag2log[$tag]="${tag2log[$tag]},\n\t$log"
	fi
	#echo -e "$tag;$msg;$log"
}

for log in $(cat crash.lst kasan.lst); do
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
	#echo -e "00000000;TODO;$log"
	#tag2msg[000000]="TODO"
	#tag2log[000000]="$log"
done

rm crash.lst
rm timeo.lst
rm kasan.lst


for tag in ${!tag2msg[*]}; do
	echo -e "[$tag] ${tag2msg[$tag]};\n${tag2log[$tag]}"
done > summary.txt

#for tag in ${!tag2msg[*]}; do
#	echo '<p>'
#	echo -e "[$tag] ${tag2msg[$tag]};"
#	logs="$(echo "${tag2log[$tag]}"|tr -d '\n\t'|tr ',' ' ')"
#	logs="$(echo $logs|tr -d '\\n\\t'|tr ',' ' ')"
#	for log in $logs; do
#		echo "\t<a href="$log">$log</a>"
#	done
#	echo '</p>'
#done > summary.html
