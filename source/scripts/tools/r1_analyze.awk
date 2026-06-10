NR>1 {
    total++
    if ($9 == "200") ok++
    else if ($9 == "0") f0++
    lan = $4; lt[lan]++; if ($9 != "200") lf[lan]++
    phase = $2; pt[phase]++; if ($9 != "200") pf[phase]++
}
END {
    printf "Total: %d  OK: %d  Fail-0: %d  Rate: %.2f%%\n", total, ok, f0, (total-ok)/total*100
    print ""
    print "By LAN:"
    for (l in lt) printf "  %s: %d/%d (%.1f%%)\n", l, lf[l], lt[l], lf[l]/lt[l]*100
    print ""
    print "By phase:"
    for (p in pt) printf "  %-30s %6d %6d %5.1f%%\n", p, pt[p], pf[p], pf[p]/pt[p]*100
}
