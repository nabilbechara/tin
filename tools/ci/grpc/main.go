// A gRPC client (grpc-go) for examples/grpc.tin, run by tools/ci/h2_check.py (#360). It calls
// helloworld.Greeter/SayHello with wrapperspb.StringValue, whose single string field 1 is
// wire-identical to HelloRequest and HelloReply, so no generated code is needed.
package main

import (
	"context"
	"flag"
	"fmt"
	"os"
	"strings"
	"sync"
	"time"

	"google.golang.org/grpc"
	"google.golang.org/grpc/codes"
	"google.golang.org/grpc/credentials/insecure"
	"google.golang.org/grpc/status"
	"google.golang.org/protobuf/types/known/wrapperspb"
)

const method = "/helloworld.Greeter/SayHello"

func fail(format string, args ...any) {
	fmt.Fprintf(os.Stderr, "FAIL "+format+"\n", args...)
	os.Exit(1)
}

func main() {
	addr := flag.String("addr", "127.0.0.1:50051", "the server")
	flag.Parse()
	conn, err := grpc.NewClient(*addr, grpc.WithTransportCredentials(insecure.NewCredentials()),
		grpc.WithDefaultCallOptions(grpc.MaxCallRecvMsgSize(8<<20), grpc.MaxCallSendMsgSize(8<<20)))
	if err != nil {
		fail("dial: %v", err)
	}
	defer conn.Close()
	ctx, cancel := context.WithTimeout(context.Background(), 20*time.Second)
	defer cancel()

	out := new(wrapperspb.StringValue)
	if err := conn.Invoke(ctx, method, wrapperspb.String("tin"), out); err != nil {
		fail("SayHello: %v", err)
	}
	if out.GetValue() != "Hello tin" {
		fail("SayHello replied %q", out.GetValue())
	}
	fmt.Println("PASS unary call: Hello tin")

	err = conn.Invoke(ctx, method, wrapperspb.String(""), out)
	if status.Code(err) != codes.InvalidArgument || status.Convert(err).Message() != "name is required" {
		fail("empty name: %v", err)
	}
	fmt.Println("PASS status in trailers:", status.Code(err), status.Convert(err).Message())

	err = conn.Invoke(ctx, "/helloworld.Greeter/Missing", wrapperspb.String("x"), out)
	if status.Code(err) != codes.Unimplemented {
		fail("unknown method: %v", err)
	}
	fmt.Println("PASS unknown method:", status.Code(err))

	big := strings.Repeat("é", 1<<20) // 2 MiB each way: flow control in both directions
	if err := conn.Invoke(ctx, method, wrapperspb.String(big), out); err != nil {
		fail("big call: %v", err)
	}
	if out.GetValue() != "Hello "+big {
		fail("big call replied %d bytes", len(out.GetValue()))
	}
	fmt.Println("PASS 2 MiB request and reply")

	var wg sync.WaitGroup
	errs := make(chan error, 200)
	for i := 0; i < 200; i++ {
		wg.Add(1)
		go func(i int) {
			defer wg.Done()
			name := fmt.Sprintf("caller %d", i)
			o := new(wrapperspb.StringValue)
			if err := conn.Invoke(ctx, method, wrapperspb.String(name), o); err != nil {
				errs <- err
				return
			}
			if o.GetValue() != "Hello "+name {
				errs <- fmt.Errorf("caller %d got %q", i, o.GetValue())
			}
		}(i)
	}
	wg.Wait()
	close(errs)
	for err := range errs {
		fail("concurrent calls: %v", err)
	}
	fmt.Println("PASS 200 concurrent calls on one connection")
}
