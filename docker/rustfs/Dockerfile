FROM rustfs/rustfs:1.0.6@sha256:ee717072290bec9b11abfc0365f8310b00df1cd9b3639943edae47bdef05044a

USER root
COPY docker/rustfs/entrypoint.sh /usr/local/bin/mtp-rustfs-entrypoint.sh
RUN chmod 0755 /usr/local/bin/mtp-rustfs-entrypoint.sh

ENTRYPOINT ["/usr/local/bin/mtp-rustfs-entrypoint.sh"]
