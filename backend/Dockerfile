FROM maven:3.9-eclipse-temurin-17
WORKDIR /app
COPY settings.xml /root/.m2/settings.xml
COPY pom.xml .
RUN mvn dependency:go-offline -B
COPY src ./src
RUN mvn package -DskipTests -B && \
    cp target/*.jar app.jar && \
    rm -rf target /root/.m2/repository
EXPOSE 8080
CMD ["java", "-jar", "app.jar"]
