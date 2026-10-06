// Reference for toolchain/tests/v2/tide.tin: the same cases through Go's time package.
package main

import (
	"fmt"
	"math"
	"net/http"
	"time"
)

func errStr(err error) string {
	if err == nil {
		return "<nil>"
	}
	return err.Error()
}

func isLeap(y int64) bool {
	return y%4 == 0 && (y%100 != 0 || y%400 == 0)
}

func daysIn(y, m int64) int64 {
	if m < 1 || m > 12 {
		return 0
	}
	return int64(time.Date(int(y), time.Month(m+1), 0, 0, 0, 0, 0, time.UTC).Day())
}

func daysFromCivil(y, m, d int64) int64 {
	sec := time.Date(int(y), time.Month(m), int(d), 0, 0, 0, 0, time.UTC).Unix()
	return sec / 86400
}

func civilFromDays(z int64) (int64, int64, int64) {
	t := time.Unix(z*86400, 0).UTC()
	return int64(t.Year()), int64(t.Month()), int64(t.Day())
}

func weekdayName(d int64) string {
	return time.Weekday(d).String()
}

func monthName(m int64) string {
	return time.Month(m).String()
}

func utc(ns int64) time.Time {
	return time.Unix(0, ns).UTC()
}

func date(y, m, d, h, mi, s, ns int64) int64 {
	return time.Date(int(y), time.Month(m), int(d), int(h), int(mi), int(s), int(ns), time.UTC).UnixNano()
}

func main() {
	fmt.Println("consts", int64(time.Nanosecond), int64(time.Microsecond), int64(time.Millisecond), int64(time.Second), int64(time.Minute), int64(time.Hour), int(time.Sunday), int(time.Saturday))
	fmt.Println("clock", true, true, true, true, true, true)

	durs := []int64{0, 1, 999, 1000, 1001, 1500, 999999, 1000000, 1500000, 250000000, 999999999, int64(time.Second), 1500000000, 1000000001, 61 * int64(time.Second), 3661 * int64(time.Second), int64(time.Hour), 90 * int64(time.Minute), 100 * int64(time.Hour), 365 * 24 * int64(time.Hour), -1, -1500, -1500000, -1500000000, -3661 * int64(time.Second), math.MaxInt64, math.MinInt64, 59999999999, 60000000000, 3599999999999, 123456789012345}
	for _, d := range durs {
		dd := time.Duration(d)
		fmt.Println("fmtdur", d, dd.String(), fmt.Sprintf("%.6f %.6f %.6f", dd.Seconds(), dd.Minutes(), dd.Hours()), dd.Milliseconds(), dd.Microseconds())
	}

	pd := []string{"0", "+0", "-0", "1s", "1.5s", "250ms", "1h2m3s", "-1.5h", "+2m", "1us", "1µs", "1μs", "1ns", "1h1m1s1ms1us1ns", ".5s", "1.s", "0.0000001h", "100000h", "2562047h47m16.854775807s", "-2562047h47m16.854775808s", "1.000000001s", "0.1us", "1.9999999999999999999s", "1h0m0s", "00001s", "1.5m1.5s", "9223372036854775807ns", "-9223372036854775808ns", "0.5h0.5m", "1.5µs", "3.000000000000000000000001s",
		"", "x", "1", "1x", ".s", "-", "+", "-.", "1h-2m", "9223372036854775808ns", "2562047h47m16.854775808s", "1.5.5s", " 1s", "1 s", "1é", "1hs", "1s ", "3000000h", "9223372036854775808ms", "..5s", "1.2.3", "1S", "1Ms", "1\"s", "1\\s", "1\x01s", "-0x", "1e3s", "1,5s", "1.5 h"}
	for _, s := range pd {
		v, err := time.ParseDuration(s)
		fmt.Println("parsedur", fmt.Sprintf("%q", s), int64(v), errStr(err))
	}

	sec := int64(time.Second)
	stamps := []int64{0, -1, 1, 999999999, sec, 86399 * sec, 86400*sec - 1, 86400 * sec, -86400 * sec, 951782400 * sec, 951868799 * sec, 1709164800 * sec, 4107542400 * sec, -2208988800 * sec, -2208988800*sec - 1, 1759317725 * sec, math.MaxInt64, math.MinInt64, 1234567890123456789, -1234567890123456789, 2147483647 * sec, 4102444800*sec - 1, 1759317725123000000, 1759317725000000100, -7857129600 * sec}
	for _, ns := range stamps {
		t := utc(ns)
		rt := time.Date(t.Year(), t.Month(), t.Day(), t.Hour(), t.Minute(), t.Second(), t.Nanosecond(), time.UTC).UnixNano() == ns
		fmt.Println("utc", ns, t.Year(), int(t.Month()), t.Day(), t.Hour(), t.Minute(), t.Second(), t.Nanosecond(), int(t.Weekday()), t.YearDay(), rt, t.Unix(), t.Format(time.RFC3339), t.Format(time.RFC3339Nano), t.Weekday().String(), t.Month().String())
	}

	fmt.Println("date", date(2026, 10, 1, 11, 22, 5, 0), date(2026, 13, 1, 0, 0, 0, 0), date(2026, 0, 1, 0, 0, 0, 0), date(2026, -11, 1, 0, 0, 0, 0), date(2026, 1, 32, 0, 0, 0, 0), date(2026, 1, 0, 0, 0, 0, 0), date(2026, 2, 30, 25, 61, 61, 1500000000), date(2024, 2, 29, 0, 0, 0, 0), date(2023, 2, 29, 0, 0, 0, 0), date(1970, 1, 1, 0, 0, 0, -1), date(1969, 12, 31, 23, 59, 59, 999999999), date(2026, 25, -5, -1, -1, -1, -1), date(1677, 9, 21, 0, 12, 43, 145224192), date(2262, 4, 11, 23, 47, 16, 854775807))
	fmt.Println("unix civil", date(2026, 10, 1, 11, 22, 5, 7), time.Date(1969, 12, 31, 23, 59, 59, 1, time.UTC).Unix(), time.Date(1970, 1, 1, 0, 0, 0, 0, time.UTC).Unix())

	rfc := []string{"2026-10-01T11:22:05Z", "2026-10-01T11:22:05.5Z", "2026-10-01T11:22:05.123456789Z", "2026-10-01T11:22:05.1234567891234Z", "2026-10-01T11:22:05.000000001Z", "2026-10-01T11:22:05+02:00", "2026-10-01T11:22:05-07:30", "2026-10-01T11:22:05.25-00:00", "2026-10-01T5:22:05Z", "2026-10-01T11:22:05,5Z", "2024-02-29T00:00:00Z", "1700-01-01T00:00:00Z", "1969-12-31T23:59:59.999999999Z", "2262-04-11T23:47:16.854775807Z", "1677-09-21T00:12:43.145224192Z", "2026-10-01T11:22:05+24:00", "2026-10-01T11:22:05+02:60", "2026-10-01T23:59:59Z", "2026-12-31T23:59:59+23:59", "2026-10-01T11:22:05.5+02:00", "2026-10-01T11:22:05-24:00", "2026-10-01T11:22:05.1234567890123456789Z", "2026-10-01T0:00:00Z", "2026-10-01T11:22:05.000Z", "2026-10-01T11:22:05.100Z",
		"", "2026-10-01", "2026-10-01 11:22:05Z", "2026-10-01t11:22:05Z", "2026-10-01T11:22:05z", "2026-13-01T11:22:05Z", "2026-00-01T11:22:05Z", "2026-10-00T11:22:05Z", "2026-02-30T11:22:05Z", "2023-02-29T00:00:00Z", "2026-10-01T24:00:00Z", "2026-10-01T11:60:05Z", "2026-10-01T11:22:60Z", "2026-10-01T11:22:05", "2026-10-01T11:22:05+0200", "2026-10-01T11:22:05+25:00", "2026-10-01T11:22:05+02:61", "2026-10-01T11:22:05Zjunk", "2026-10-01T11:22:05.Z", "2026-10-01T11:22:05.", "2026-1-01T11:22:05Z", "26-10-01T11:22:05Z", "2026-10-01T11:22:05.5", "2026-10-01T11:22:5Z", "2026-10-01T011:22:05Z", "2026-10-01T11:22:05 Z", " 2026-10-01T11:22:05Z", "2026-10-01T11:22:05Z ", "2026/10/01T11:22:05Z", "2026-10-01T11:22:05+2:00", "2026-10-01T11:22:05+02:0", "202a-10-01T11:22:05Z", "2026-10-01T11:22:05Ж", "2026-10-01T11:22:05.5ZZ", "2026-10-01T11:22:05*02:00", "2026-10-01T11:22:05+0a:00", "2026-10-01T11:2a:05Z", "2026-10-01T1a:22:05Z", "2026-10-0aT11:22:05Z", "2026-1a-01T11:22:05Z", "2026-10-01T11:22:05+02-00", "2026-10-01T11:22:05-1:30"}
	for _, s := range rfc {
		t, err := time.Parse(time.RFC3339, s)
		if err != nil {
			fmt.Println("parserfc", fmt.Sprintf("%q", s), "fault")
		} else {
			fmt.Println("parserfc", fmt.Sprintf("%q", s), t.UnixNano(), t.UTC().Format(time.RFC3339Nano))
		}
	}

	secs := []int64{0, -1, 1759317725, 951782400, 4107542400, -2208988800, 253402300799, 2147483647, 86400 * 365, 253402300800, -62167219200, -62167219201, math.MaxInt64}
	for _, s := range secs {
		fmt.Println("http", s, time.Unix(s, 0).UTC().Format(http.TimeFormat))
	}

	years := []int64{1900, 2000, 2023, 2024, 2100, 2400, 0, -1, -4, -100, -400, 1, 1970}
	for _, y := range years {
		fmt.Println("leap", y, isLeap(y), daysIn(y, 1), daysIn(y, 2), daysIn(y, 4), daysIn(y, 12), daysIn(y, 0), daysIn(y, 13))
	}

	fmt.Println("names", weekdayName(0), weekdayName(6), weekdayName(7), weekdayName(-1), monthName(1), monthName(9), monthName(12), monthName(0), monthName(13))
	fmt.Println("daysfrom", daysFromCivil(1970, 1, 1), daysFromCivil(2000, 3, 1), daysFromCivil(1600, 1, 1), daysFromCivil(-1, 12, 31), daysFromCivil(2026, 10, 1), daysFromCivil(1969, 12, 31), daysFromCivil(2026, 2, 30), daysFromCivil(400, 1, 1), daysFromCivil(0, 1, 1))
	zs := []int64{0, -1, 1, 11016, 20729, 719162, -719468, -1096, 2932896, -2000000, 146097, -146097}
	for _, z := range zs {
		y, m, d := civilFromDays(z)
		fmt.Println("civilfrom", z, y, m, d, daysFromCivil(y, m, d) == z)
	}
}
