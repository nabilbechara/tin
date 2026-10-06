// A gRPC server (grpc-go) for wire's HTTP/2 client (#480), run by tools/ci/h2_check.py:
// helloworld.Greeter/SayHello over cleartext HTTP/2, with wrapperspb.StringValue in place of
// HelloRequest and HelloReply (the same bytes on the wire), so no generated code is needed. An
// empty name is INVALID_ARGUMENT.
package main

import (
	"context"
	"flag"
	"fmt"
	"net"
	"os"

	"google.golang.org/grpc"
	"google.golang.org/grpc/codes"
	"google.golang.org/grpc/status"
	"google.golang.org/protobuf/types/known/wrapperspb"
)

func sayHello(srv any, ctx context.Context, dec func(any) error, _ grpc.UnaryServerInterceptor) (any, error) {
	in := new(wrapperspb.StringValue)
	if err := dec(in); err != nil {
		return nil, err
	}
	if in.Value == "" {
		return nil, status.Error(codes.InvalidArgument, "name is required")
	}
	return wrapperspb.String("Hello " + in.Value), nil
}

var greeter = grpc.ServiceDesc{
	ServiceName: "helloworld.Greeter",
	HandlerType: (*any)(nil),
	Methods:     []grpc.MethodDesc{{MethodName: "SayHello", Handler: sayHello}},
	Metadata:    "helloworld.proto",
}

func main() {
	addr := flag.String("addr", "127.0.0.1:50052", "the address to listen on")
	flag.Parse()
	ln, err := net.Listen("tcp", *addr)
	if err != nil {
		fmt.Fprintln(os.Stderr, err)
		os.Exit(1)
	}
	s := grpc.NewServer()
	s.RegisterService(&greeter, struct{}{})
	fmt.Println("listening")
	if err := s.Serve(ln); err != nil {
		fmt.Fprintln(os.Stderr, err)
		os.Exit(1)
	}
}
