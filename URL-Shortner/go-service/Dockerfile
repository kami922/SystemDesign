FROM golang:1.25 AS build

WORKDIR /src
COPY . .
RUN CGO_ENABLED=0 go build -mod=vendor -o /out/server ./cmd/server

FROM alpine:3.20
RUN apk add --no-cache ca-certificates
COPY --from=build /out/server /server

EXPOSE 8080
ENTRYPOINT ["/server"]
