package org.tb.quarkus.controller;

import io.smallrye.reactive.messaging.MutinyEmitter;
import jakarta.ws.rs.POST;
import jakarta.ws.rs.Path;
import jakarta.ws.rs.PathParam;
import org.eclipse.microprofile.reactive.messaging.Channel;

@Path("/prices")
public class PriceResource {

    @Channel("prices")
    MutinyEmitter<Double> emitter;

    @POST
    @Path("/{price}")
    public void publish(@PathParam("price") double price) {
        emitter.sendAndAwait(price);
    }
}