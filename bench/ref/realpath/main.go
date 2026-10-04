package main
import("fmt";"os";"path/filepath")
func main(){for _,path:=range os.Args[1:]{if path==""{fmt.Println("<nil>");continue};p,err:=filepath.EvalSymlinks(path);if err!=nil{fmt.Println("<nil>");continue};p,err=filepath.Abs(p);if err!=nil{fmt.Println("<nil>")}else{fmt.Println(p)}}}
