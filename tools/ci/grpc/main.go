// A gRPC client (grpc-go) for examples/grpc.tin, run by tools/ci/h2_check.py (#360). It calls
// helloworld.Greeter/SayHello with wrapperspb.StringValue, whose single string field 1 is
// wire-identical to HelloRequest and HelloReply, so no generated code is needed.
package main

import (
	"context"
	"flag"
	"fmt"
	"io"
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

	// Client streaming (#481): the server reads the names as they arrive and answers once.
	cs, err := conn.NewStream(ctx, &grpc.StreamDesc{ClientStreams: true}, "/helloworld.Greeter/SayHelloAll")
	if err != nil {
		fail("SayHelloAll: %v", err)
	}
	for _, n := range []string{"a", "b", "c"} {
		if err := cs.SendMsg(wrapperspb.String(n)); err != nil {
			fail("SayHelloAll send: %v", err)
		}
	}
	if err := cs.CloseSend(); err != nil {
		fail("SayHelloAll close: %v", err)
	}
	all := new(wrapperspb.StringValue)
	if err := cs.RecvMsg(all); err != nil || all.GetValue() != "Hello a, b, c" {
		fail("SayHelloAll replied %q: %v", all.GetValue(), err)
	}
	fmt.Println("PASS client streaming: three names, one reply")

	// Bidirectional (#481): each name is answered before the next is sent.
	bs, err := conn.NewStream(ctx, &grpc.StreamDesc{ClientStreams: true, ServerStreams: true}, "/helloworld.Greeter/Chat")
	if err != nil {
		fail("Chat: %v", err)
	}
	for _, n := range []string{"one", "two", "three"} {
		if err := bs.SendMsg(wrapperspb.String(n)); err != nil {
			fail("Chat send: %v", err)
		}
		reply := new(wrapperspb.StringValue)
		if err := bs.RecvMsg(reply); err != nil || reply.GetValue() != "Hello "+n {
			fail("Chat replied %q to %s: %v", reply.GetValue(), n, err)
		}
	}
	bs.CloseSend()
	if err := bs.RecvMsg(new(wrapperspb.StringValue)); err != io.EOF {
		fail("Chat end: %v", err)
	}
	fmt.Println("PASS bidirectional streaming: each name answered before the next is sent")

	// A long bidirectional stream: 2000 messages of 32 KiB each way (62 MiB), sent while the
	// replies are read, so both directions move through their flow-control windows.
	ls, err := conn.NewStream(ctx, &grpc.StreamDesc{ClientStreams: true, ServerStreams: true}, "/helloworld.Greeter/Chat")
	if err != nil {
		fail("long Chat: %v", err)
	}
	piece := strings.Repeat("x", 32<<10)
	got := make(chan error, 1)
	go func() {
		for i := 0; i < 2000; i++ {
			reply := new(wrapperspb.StringValue)
			if err := ls.RecvMsg(reply); err != nil {
				got <- fmt.Errorf("reply %d: %v", i, err)
				return
			}
			if reply.GetValue() != "Hello "+piece {
				got <- fmt.Errorf("reply %d has %d bytes", i, len(reply.GetValue()))
				return
			}
		}
		if err := ls.RecvMsg(new(wrapperspb.StringValue)); err != io.EOF {
			got <- fmt.Errorf("end: %v", err)
			return
		}
		got <- nil
	}()
	for i := 0; i < 2000; i++ {
		if err := ls.SendMsg(wrapperspb.String(piece)); err != nil {
			fail("long Chat send %d: %v", i, err)
		}
	}
	ls.CloseSend()
	if err := <-got; err != nil {
		fail("long Chat: %v", err)
	}
	fmt.Println("PASS bidirectional streaming: 2000 messages of 32 KiB each way")
}
