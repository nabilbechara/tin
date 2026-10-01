package main

import (
	"fmt"
	"math"
)

const PI = 3.141592653589793
const DAYS_PER_YEAR = 365.24

type Body struct {
	x, y, z, vx, vy, vz, mass float64
}

func advance(bodies []Body, dt float64) {
	n := len(bodies)
	for i := 0; i < n; i++ {
		bi := &bodies[i]
		for j := i + 1; j < n; j++ {
			bj := &bodies[j]
			dx := bi.x - bj.x
			dy := bi.y - bj.y
			dz := bi.z - bj.z
			dsq := dx*dx + dy*dy + dz*dz
			dist := math.Sqrt(dsq)
			mag := dt / (dsq * dist)
			bi.vx -= dx * bj.mass * mag
			bi.vy -= dy * bj.mass * mag
			bi.vz -= dz * bj.mass * mag
			bj.vx += dx * bi.mass * mag
			bj.vy += dy * bi.mass * mag
			bj.vz += dz * bi.mass * mag
		}
	}
	for i := 0; i < n; i++ {
		b := &bodies[i]
		b.x += dt * b.vx
		b.y += dt * b.vy
		b.z += dt * b.vz
	}
}

func energy(bodies []Body) float64 {
	e := 0.0
	n := len(bodies)
	for i := 0; i < n; i++ {
		b := &bodies[i]
		e += 0.5 * b.mass * (b.vx*b.vx + b.vy*b.vy + b.vz*b.vz)
		for j := i + 1; j < n; j++ {
			b2 := &bodies[j]
			dx := b.x - b2.x
			dy := b.y - b2.y
			dz := b.z - b2.z
			e -= (b.mass * b2.mass) / math.Sqrt(dx*dx+dy*dy+dz*dz)
		}
	}
	return e
}

func main() {
	solarMass := 4.0 * PI * PI
	bodies := []Body{
		{mass: solarMass},
		{x: 4.84143144246472090, y: -1.16032004402742839, z: -0.103622044471123109, vx: 0.00166007664274403694 * DAYS_PER_YEAR, vy: 0.00769901118419740425 * DAYS_PER_YEAR, vz: -0.0000690460016972063023 * DAYS_PER_YEAR, mass: 0.000954791938424326609 * solarMass},
		{x: 8.34336671824457987, y: 4.12479856412430479, z: -0.403523417114321381, vx: -0.00276742510726862411 * DAYS_PER_YEAR, vy: 0.00499852801234917238 * DAYS_PER_YEAR, vz: 0.0000230417297573763929 * DAYS_PER_YEAR, mass: 0.000285885980666130812 * solarMass},
		{x: 12.8943695621391310, y: -15.1111514016986312, z: -0.223307578892655734, vx: 0.00296460137564761618 * DAYS_PER_YEAR, vy: 0.00237847173959480950 * DAYS_PER_YEAR, vz: -0.0000296589568540237556 * DAYS_PER_YEAR, mass: 0.0000436624404335156298 * solarMass},
		{x: 15.3796971148509165, y: -25.9193146099879641, z: 0.179258772950371181, vx: 0.00268067772490389322 * DAYS_PER_YEAR, vy: 0.00162824170038242295 * DAYS_PER_YEAR, vz: -0.0000951592254519715870 * DAYS_PER_YEAR, mass: 0.0000515138902046611451 * solarMass},
	}
	px, py, pz := 0.0, 0.0, 0.0
	for _, b := range bodies {
		px += b.vx * b.mass
		py += b.vy * b.mass
		pz += b.vz * b.mass
	}
	sun := &bodies[0]
	sun.vx = -px / solarMass
	sun.vy = -py / solarMass
	sun.vz = -pz / solarMass
	fmt.Printf("%.9f\n", energy(bodies))
	for i := 0; i < 50000000; i++ {
		advance(bodies, 0.01)
	}
	fmt.Printf("%.9f\n", energy(bodies))
}
