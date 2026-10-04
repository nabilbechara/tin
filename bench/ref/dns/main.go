package main
import("context";"fmt";"net";"os";"time")
func main() {
    server:=os.Args[1]
    resolver:=&net.Resolver{PreferGo:true,Dial:func(ctx context.Context,network,address string)(net.Conn,error){return (&net.Dialer{}).DialContext(ctx,network,server)}}
    for _,name:=range os.Args[2:] {
        ctx,cancel:=context.WithTimeout(context.Background(),time.Second*3)
        ips,err:=resolver.LookupIP(ctx,"ip",name);cancel();if err!=nil{panic(err)}
        chosen:=ips[0];for _,ip:=range ips{if ip.To4()!=nil{chosen=ip;break}}
        if v4:=chosen.To4();v4!=nil{fmt.Printf("2:%x\n",[]byte(v4))}else{fmt.Printf("10:%x\n",[]byte(chosen.To16()))}
    }
}
