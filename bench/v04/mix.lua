-- wrk2 script: GET <prefix><random id in 1..10000>, and /slow for a share of requests.
-- wrk ... -s mix.lua <url> -- <prefix> <slow percent>
local prefix = "/users/"
local slow = 0

function init(args)
  if args[1] then prefix = args[1] end
  if args[2] then slow = tonumber(args[2]) end
  math.randomseed(os.time() + math.floor(os.clock() * 1000000))
end

function request()
  if slow > 0 and math.random() * 100 < slow then
    return wrk.format("GET", "/slow")
  end
  return wrk.format("GET", prefix .. math.random(1, 10000))
end
