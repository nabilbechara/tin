package main
import("bufio"; "fmt"; "os"; "strconv"; "time")
func main() {
    width,_:=strconv.Atoi(os.Args[1])
    in:=bufio.NewReader(os.Stdin)
    for { var seconds int64; if _,err:=fmt.Fscan(in,&seconds);err!=nil{return}; t:=time.Unix(seconds,0).UTC()
        y,m,d:=t.Date(); h,minute,s:=t.Clock()
        date:=fmt.Sprintf("Date: %s, %02d %s %0*d %02d:%02d:%02d GMT\r\n",t.Weekday().String()[:3],d,m.String()[:3],width,y,h,minute,s)
        fmt.Printf("%d %d %d %d %d %d %d %q\n",y,m,d,h,minute,s,t.Weekday(),date)
    }
}
