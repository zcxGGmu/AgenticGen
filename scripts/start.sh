#!/bin/bash

# AgenticGen 启动脚本

set -e

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# 打印带颜色的消息
print_message() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# 检查Docker是否安装
check_docker() {
    if ! command -v docker &> /dev/null; then
        print_error "Docker未安装，请先安装Docker"
        exit 1
    fi

    if ! command -v docker-compose &> /dev/null && ! docker compose version &> /dev/null; then
        print_error "Docker Compose未安装，请先安装Docker Compose"
        exit 1
    fi
}

# 检查环境文件
check_env_file() {
    if [ ! -f ".env" ]; then
        print_warning ".env文件不存在，正在从.env.example创建..."
        cp deployment/.env.example .env
        print_warning "请编辑.env文件配置必要的环境变量，特别是OPENAI_API_KEY"
        return 1
    fi

    # 检查必要的环境变量
    source .env

    if [ -z "$OPENAI_API_KEY" ] || [ "$OPENAI_API_KEY" = "your_openai_api_key_here" ]; then
        print_error "请在.env文件中配置有效的OPENAI_API_KEY"
        return 1
    fi

    return 0
}

# 创建必要的目录
create_directories() {
    print_message "创建必要的目录..."
    mkdir -p logs
    mkdir -p uploads
    mkdir -p data/vector_db
    mkdir -p deployment/ssl
}

# 构建镜像
build_images() {
    print_message "构建Docker镜像..."
    docker-compose -f deployment/docker-compose.yml build --no-cache
}

# 启动服务
start_services() {
    print_message "启动AgenticGen服务..."
    docker-compose -f deployment/docker-compose.yml up -d

    # 等待服务启动
    print_message "等待服务启动..."
    sleep 10

    # 检查服务状态
    print_message "检查服务状态..."
    docker-compose -f deployment/docker-compose.yml ps

    # 等待数据库初始化
    print_message "等待数据库初始化..."
    sleep 20

    # 运行数据库迁移
    print_message "运行数据库迁移..."
    docker-compose -f deployment/docker-compose.yml exec -T app python -m alembic upgrade head

    print_message "服务启动完成！"
    print_message "访问地址: http://localhost:9000"
    print_message "API文档: http://localhost:9000/docs"
}

# 显示日志
show_logs() {
    if [ "$1" = "-f" ]; then
        docker-compose -f deployment/docker-compose.yml logs -f
    else
        docker-compose -f deployment/docker-compose.yml logs
    fi
}

# 停止服务
stop_services() {
    print_message "停止AgenticGen服务..."
    docker-compose -f deployment/docker-compose.yml down
    print_message "服务已停止"
}

# 重启服务
restart_services() {
    print_message "重启AgenticGen服务..."
    docker-compose -f deployment/docker-compose.yml restart
    print_message "服务已重启"
}

# 清理资源
cleanup() {
    print_message "清理Docker资源..."
    docker-compose -f deployment/docker-compose.yml down -v --remove-orphans
    docker system prune -f
    print_message "清理完成"
}

# 显示帮助信息
show_help() {
    echo "AgenticGen 启动脚本"
    echo ""
    echo "用法: $0 [命令]"
    echo ""
    echo "命令:"
    echo "  start       启动服务（默认）"
    echo "  stop        停止服务"
    echo "  restart     重启服务"
    echo "  logs        显示日志"
    echo "  logs -f     实时显示日志"
    echo "  build       重新构建镜像"
    echo "  cleanup     清理所有资源"
    echo "  help        显示此帮助信息"
    echo ""
    echo "示例:"
    echo "  $0 start    # 启动服务"
    echo "  $0 logs -f  # 实时查看日志"
}

# 主函数
main() {
    # 检查Docker
    check_docker

    # 解析命令行参数
    case "${1:-start}" in
        "start")
            if ! check_env_file; then
                exit 1
            fi
            create_directories
            build_images
            start_services
            ;;
        "stop")
            stop_services
            ;;
        "restart")
            restart_services
            ;;
        "logs")
            show_logs "$2"
            ;;
        "build")
            build_images
            ;;
        "cleanup")
            cleanup
            ;;
        "help"|"-h"|"--help")
            show_help
            ;;
        *)
            print_error "未知命令: $1"
            show_help
            exit 1
            ;;
    esac
}

# 执行主函数
main "$@"